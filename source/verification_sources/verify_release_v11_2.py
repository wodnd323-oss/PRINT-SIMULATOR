"""Read-only HARDYS V11.2 release gate for the bundled Windows runtime.

Run from the bundle root:
  runtime/python/python.exe verification_sources/verify_release_v11_2.py --output result.json

Linux development comparison only:
  python3 verification_sources/verify_release_v11_2.py --native-gs --output result.json

Only stdlib, numpy, Pillow and pypdf are used. All generated PDF/render files
live in a TemporaryDirectory; no server, user calibration or catalog is opened.
Windows default execution invokes the actual gs_bridge.py and GS 9.50 DLL.
A remote Windows CI result is not verification of the user's installed PC.
"""
import argparse
import ast
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

sys.dont_write_bytecode = True
APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
BASELINE_ZIP_SHA256 = '139032097707e870ea1e0f961cf7a72853dde8617086979a298f039e742b2d1f'
# Captured directly from the verified original V11.1 Full Install ZIP on
# 2026-11-23, not from the mutable V11.2 working directory.
ORIGINAL_HASHES = {
    'color_model.py': '6714996845ed58c7615c57084b7daa9b4d9c375495202440ddfd744b238fbffe',
    'prediction.py': '04c7d4509696dc9302183d78e177aed2ef3098f8a40a17e5963660c51d851c01',
    'default_calibration.json': '5653523ea74fb72bdfc4c60d31bca8c0e6f4b7b2ae03bbd6e576fbbd8aa75236',
    'icc/CoatedFOGRA39.icc': 'da2b9b593e27cba2563cbc8596071c5c8f2395d3dbb4434538bac2bc9d58ce77',
    'icc/GRACoL2013_CRPC6.icc': '4ebbfad6bc9cfc033fdafdd8ac5df8159208932cb16d9a6596d349ae7ab50443',
    'reference_archive/delivered_case7.pdf': 'e8cf05c8b3241d037ea40214213a95551a3ad24e49e001894b30c65b6bdcb23a',
    'assets/reference_v11/page_01_source.png': 'c48696c95adb4211371a06128306f01202808ff7d08cd22b9308c8c053c3b41d',
    'assets/printed_case_reference.png': '0704f99348a971c07f7fef83505bb89ed30996ac7350d6602a159f18f9061749',
    'gs_bridge.py': 'e1afe2793d7f5b64778d70c6d15079cd4c25616298d4c33f356951158f1ef7bf',
    'runtime/ghostscript/bin/gsdll64.dll': '85cb1e23c4a6db2c3f1122b7daf97fa0c502953ad400eb027ea3e4c34e8fcb15',
}
# Only CR/LF normalization and this one render_revision value may differ.
RGB_IMPORTER_NORMALIZED_SHA256 = '8f6ac385b8c76347a02bab43add1d8cbd5d4c2abe6fe1348abbc48eed8da1f0b'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def need(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-gs', action='store_true', help='Development comparison only; never a Windows release gate.')
    args = parser.parse_args()
    started = time.monotonic()
    result = {'schema_version': 1, 'revision': '11.2',
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'baseline_zip_sha256': BASELINE_ZIP_SHA256,
              'mode': 'native_development_comparison' if args.native_gs else 'bundled_windows_release_gate',
              'scope': 'Remote/independent execution; does not verify the user PC, monitor settings, printer RIP or measured print color.',
              'environment': {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform()},
              'tests': {}, 'all_pass': False, 'release_gate_eligible': False}

    def check(name, function):
        print('RUN ' + name, flush=True)
        before = time.monotonic()
        try:
            data = function() or {}
            result['tests'][name] = {'pass': True, **data, 'seconds': round(time.monotonic() - before, 3)}
        except Exception as exc:
            result['tests'][name] = {'pass': False, 'error': str(exc), 'traceback': traceback.format_exc(),
                                     'seconds': round(time.monotonic() - before, 3)}
        print(('PASS ' if result['tests'][name]['pass'] else 'FAIL ') + name, flush=True)
        return result['tests'][name]['pass']

    try:
        import numpy as np
        from PIL import Image, ImageCms
        import pypdf
        from pypdf import PdfWriter
        from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject, TextStringObject
        import proof_pdf
        from prediction import Predictor
        from inverse_color import inverse_color
        from color_model import rgb_to_lab

        result['environment'].update(pillow=Image.__version__, lcms=ImageCms.core.littlecms_version,
                                     numpy=np.__version__, pypdf=pypdf.__version__)
        document = json.loads((APP / 'default_calibration.json').read_text(encoding='utf8'))

        def revision_check():
            tree = ast.parse((APP / 'startup_state.py').read_text(encoding='utf8'))
            assignments = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                           if isinstance(node, ast.Assign) and len(node.targets) == 1
                           and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('REVISION', 'BUILD')}
            need(assignments.get('REVISION') == '11.2', 'Startup revision is not 11.2.')
            rgb_code = (APP / 'proof_rgb_image.py').read_text(encoding='utf8')
            need(rgb_code.count("'render_revision':'11.2'") == 1, 'RGB importer revision is not exactly one 11.2 metadata field.')
            return {'startup_revision': assignments['REVISION'], 'build': assignments.get('BUILD'), 'rgb_revision': '11.2'}

        def preservation_check():
            rows = {}
            for relative, expected in ORIGINAL_HASHES.items():
                path = APP / relative
                if args.native_gs and relative.endswith('/gsdll64.dll') and not path.exists():
                    rows[relative] = {'skipped': 'Windows DLL absent in native development copy', 'expected_sha256': expected}
                    continue
                actual = sha(path)
                rows[relative] = {'actual_sha256': actual, 'expected_sha256': expected, 'equal': actual == expected}
            code = (APP / 'proof_rgb_image.py').read_text(encoding='utf8').replace('\r\n', '\n').replace('\r', '\n')
            need(code.count("'render_revision':'11.2'") == 1, 'Unexpected RGB importer revision metadata.')
            normalized = code.replace("'render_revision':'11.2'", "'render_revision':'__REVISION__'")
            normalized_sha = hashlib.sha256(normalized.encode('utf8')).hexdigest()
            rows['proof_rgb_image.py_normalized'] = {'actual_sha256': normalized_sha,
                                                    'expected_sha256': RGB_IMPORTER_NORMALIZED_SHA256,
                                                    'equal': normalized_sha == RGB_IMPORTER_NORMALIZED_SHA256,
                                                    'allowed_change': 'One render_revision value 11.1->11.2 and line endings only.'}
            result['preserved_files'] = rows
            need(all(row.get('equal', True) for row in rows.values()), 'Original core/calibration/profile/reference preservation check failed.')
            need(len(document.get('anchors', [])) == 13, 'Default calibration does not have 13 anchors.')
            return {'files_checked': len(rows), 'anchors': len(document['anchors'])}

        def engine_check():
            if args.native_gs:
                binary = shutil.which('gs')
                need(bool(binary), '--native-gs requires a native gs executable.')
                proof_pdf.gs_command = lambda: [binary]
            else:
                need(os.name == 'nt', 'Default release gate requires Windows. Use --native-gs only for development.')
                need(Path(sys.executable).resolve() == (APP / 'runtime/python/python.exe').resolve(), 'Must run with the bundled runtime/python/python.exe.')
                need(sha(APP / 'runtime/ghostscript/bin/gsdll64.dll') == ORIGINAL_HASHES['runtime/ghostscript/bin/gsdll64.dll'], 'Bundled Ghostscript DLL hash differs.')
            command = proof_pdf.gs_command()
            if not args.native_gs:
                need(len(command) == 2 and Path(command[0]).resolve() == Path(sys.executable).resolve()
                     and Path(command[1]).resolve() == (APP / 'gs_bridge.py').resolve(), 'PDF renderer is not using the actual bundled DLL bridge.')
            # --version is an informational API exit, not an interpreter run;
            # the unchanged product bridge accepts only normal
            # completion/quit. Also PostScript `version` may be a compatibility
            # string such as 3010. `revision` identifies the actual GS product.
            probe_args = ['-q', '-dNODISPLAY', '-dBATCH', '-c', 'revision == quit']
            completed = subprocess.run([*command, *probe_args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            probe_output = completed.stdout.decode('utf8', errors='replace').strip()
            result['engine_probe'] = {'command': command, 'probe_args': probe_args,
                                      'exit_code': completed.returncode, 'stdout': probe_output}
            need(completed.returncode == 0, 'Ghostscript revision execution failed: ' + probe_output)
            need(bool(re.fullmatch(r'\d+', probe_output)), 'Ghostscript revision output is not one integer: ' + probe_output)
            revision = int(probe_output)
            version = (f'{revision // 100}.{revision % 100:02d}' if revision < 1000
                       else f'{revision // 1000}.{(revision // 10) % 100:02d}.{revision % 10}')
            if not args.native_gs:
                need(revision == 950, 'Expected bundled Ghostscript revision 950, got ' + probe_output)
                need(bool(re.search(r'(?<!\d)9\.50(?!\d)', version)), 'Expected bundled Ghostscript 9.50, got ' + version)
            result['engine'] = {'command': command, 'version_output': version, 'revision': revision,
                                'probe_args': probe_args, 'probe_exit_code': completed.returncode,
                                'probe_stdout': probe_output,
                                'actual_bundled_gs950_dll': not args.native_gs,
                                'user_pc_executed': False}
            return result['engine']

        check('revision', revision_check)
        preserved = check('original_core_calibration_profiles', preservation_check)
        engine_ok = check('ghostscript_execution', engine_check)
        need(preserved and engine_ok, 'Stop rendering because the baseline or required engine check failed.')

        def array(path):
            with Image.open(path) as image:
                return np.asarray(image).astype(int)

        def difference(a, b):
            return int(np.max(np.abs(np.asarray(a).astype(float) - np.asarray(b).astype(float))))

        def centers(directory, count, filename='page_01_relative.png'):
            return array(directory / filename)[10, np.arange(count) * 20 + 10]

        def profile_stream(writer, data):
            stream = DecodedStreamObject()
            stream.set_data(data)
            stream[NameObject('/N')] = NumberObject(4 if data[16:20] == b'CMYK' else 3)
            return writer._add_object(stream)

        def fixture(path, cells, output_intent, profiles=None):
            writer = PdfWriter()
            page = writer.add_blank_page(width=len(cells) * 20, height=20)
            spaces = DictionaryObject()
            for name, data in (profiles or {}).items():
                spaces[NameObject('/' + name)] = ArrayObject([NameObject('/ICCBased'), profile_stream(writer, data)])
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/ColorSpace'): spaces})
            commands = []
            for index, (name, values) in enumerate(cells):
                color = ' '.join(f'{int(v) / 255:.9f}' for v in values)
                color_command = f'/{name} cs {color} scn' if name else f'{color} k'
                commands.append(f'q {color_command} {index * 20} 0 20 20 re f Q')
            content = DecodedStreamObject()
            content.set_data(('\n'.join(commands) + '\n').encode('ascii'))
            page[NameObject('/Contents')] = writer._add_object(content)
            intent = DictionaryObject({NameObject('/Type'): NameObject('/OutputIntent'), NameObject('/S'): NameObject('/GTS_PDFX'),
                                       NameObject('/OutputConditionIdentifier'): TextStringObject('HARDYS release verification'),
                                       NameObject('/DestOutputProfile'): profile_stream(writer, output_intent)})
            writer._root_object[NameObject('/OutputIntents')] = ArrayObject([writer._add_object(intent)])
            with path.open('wb') as stream:
                writer.write(stream)
            return path

        with tempfile.TemporaryDirectory(prefix='hardys_v112_release_') as temporary:
            temp = Path(temporary)

            def render(path, name, dpi=72):
                before = sha(path)
                directory = proof_pdf.render(path, temp / name, dpi=dpi)
                info = json.loads((directory / 'preview_info.json').read_text(encoding='utf8'))
                need(sha(path) == before and info['input_unchanged'], 'Input PDF was modified.')
                need(info.get('render_revision') == '11.2', 'PDF render metadata revision is not 11.2.')
                return directory, info

            def delivered_check():
                directory, info = render(APP / 'reference_archive/delivered_case7.pdf', 'delivered', 180)
                source = array(directory / 'page_01_source.png')
                reference = array(APP / 'assets/reference_v11/page_01_source.png')
                need(source.shape == reference.shape, 'Delivered PDF source dimensions changed.')
                tolerance = 1 if args.native_gs else 0
                rows = []
                for anchor in document['anchors']:
                    x, y = map(int, anchor['source_xy'])
                    radius = int(anchor['source_patch_radius'])
                    region = (slice(y-radius, y+radius+1), slice(x-radius, x+radius+1))
                    current = np.median(source[region].reshape(-1,3), axis=0)
                    expected = np.median(reference[region].reshape(-1,3), axis=0)
                    rows.append({'anchor': anchor['id'], 'source_median': current.tolist(), 'reference_median': expected.tolist(),
                                 'max_channel_difference': difference(current, expected)})
                result['delivered_anchor_results'] = rows
                need(all(row['max_channel_difference'] <= tolerance for row in rows), 'Delivered PDF anchor colors changed beyond the declared engine tolerance.')
                need(info['source_icc_sha256'] == ORIGINAL_HASHES['icc/GRACoL2013_CRPC6.icc'], 'Delivered PDF no longer uses the original GRACoL ICC.')
                need(not info['cmyk_preservation']['device_cmyk_default_normalized'], 'Actual GRACoL delivered PDF must not be treated as equivalent FOGRA.')
                return {'anchors': len(rows), 'maximum_channel_difference': max(row['max_channel_difference'] for row in rows),
                        'allowed_channel_difference': tolerance, 'source_icc_sha256': info['source_icc_sha256'],
                        'source_pdf_sha256': info['source_sha256']}

            raw = (APP / 'icc/CoatedFOGRA39.icc').read_bytes()
            gracol = (APP / 'icc/GRACoL2013_CRPC6.icc').read_bytes()
            a98 = (APP / 'runtime/ghostscript/iccprofiles/a98.icc').read_bytes()
            changed = bytearray(raw)
            changed[48:52] = b'TEST'
            changed[84:100] = bytes(16)
            changed = bytes(changed)
            points = np.array([[0,0,0,255], [249,54,77,220], [255,0,0,0], [0,255,255,0], [10,20,30,40], [200,100,50,100]], dtype=np.uint8)
            cells = [(None, point) for point in points]
            target = ImageCms.ImageCmsProfile(io.BytesIO(raw))
            srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
            cmyk_image = Image.frombytes('CMYK', (len(points), 1), points.tobytes())
            preserved_rgb = np.asarray(ImageCms.profileToProfile(cmyk_image, target, srgb, outputMode='RGB', renderingIntent=1, flags=0)).reshape(-1,3)

            def equivalent_check():
                path = fixture(temp / 'equivalent.pdf', cells, changed)
                directory, info = render(path, 'equivalent_render')
                actual = centers(directory, len(cells))
                need(difference(actual, preserved_rgb) == 0, 'Equivalent-header DeviceCMYK PDF does not preserve the six raster colors exactly.')
                need(info['cmyk_preservation']['device_cmyk_default_normalized'], 'Equivalent default ICC was not normalized.')
                need(info['source_icc_sha256'] == hashlib.sha256(changed).hexdigest(), 'Original OutputIntent ICC provenance changed.')
                return {'input_cmyk_8bit': points.tolist(), 'expected_rgb': preserved_rgb.tolist(), 'actual_rgb': actual.tolist(),
                        'max_channel_difference': difference(actual, preserved_rgb), 'normalization': info['cmyk_preservation']}

            def explicit_and_mixed_check():
                mixed = cells + [('OtherCMYK', point) for point in points] + [('A98', [0,255,80]), ('A98', [128,64,32])]
                profiles = {'OtherCMYK': gracol, 'A98': a98}
                modified_path = fixture(temp / 'mixed_modified.pdf', mixed, changed, profiles)
                control_path = fixture(temp / 'mixed_control.pdf', mixed, raw, profiles)
                modified, info = render(modified_path, 'mixed_modified_render')
                control, _ = render(control_path, 'mixed_control_render')
                actual = centers(modified, len(mixed))
                expected = centers(control, len(mixed))
                object_change = difference(actual[6:], expected[6:])
                source_change = difference(array(modified / 'page_01_source.png'), array(control / 'page_01_source.png'))
                need(object_change == 0, 'Default ICC normalization changed explicit GRACoL/A98 object colors.')
                need(source_change == 0, 'Header-only OutputIntent variation changed the direct source/photo input.')
                need(difference(actual[:6], preserved_rgb) == 0, 'Mixed document DeviceCMYK colors were not preserved.')
                hashes = sorted(item['sha256'] for item in info['source_object_icc_profiles'])
                need(hashes == sorted(hashlib.sha256(data).hexdigest() for data in profiles.values()), 'Explicit object ICC provenance changed.')
                explicit_path = fixture(temp / 'explicit_equivalent.pdf', [('Equivalent', point) for point in points], raw, {'Equivalent': changed})
                explicit, explicit_info = render(explicit_path, 'explicit_equivalent_render')
                need(bool(explicit_info['warnings']), 'Unchanged equivalent explicit ICC must report its remaining boundary.')
                need(explicit_info['source_object_icc_profiles'][0]['sha256'] == hashlib.sha256(changed).hexdigest(), 'Equivalent explicit object ICC was rewritten.')
                need(not explicit_info['cmyk_preservation']['object_profiles_rewritten'], 'Object ICC rewrite unexpectedly enabled.')
                return {'explicit_gracol_a98_max_change': object_change, 'photo_source_max_change': source_change,
                        'object_icc_sha256': hashes, 'explicit_equivalent_warnings': explicit_info['warnings'],
                        'explicit_equivalent_remaining_raster_difference': difference(centers(explicit, len(points)), preserved_rgb)}

            def inverse_check():
                rows = []
                cases = [('photo', 1.0, [50,86,120]), ('photo', 0.4, [40,150,70]), ('icc', 0.0, [50,86,120])]
                for mode, strength, target_rgb in cases:
                    request = {'rgb': target_rgb, 'model_mode': mode, 'strength': strength, 'tac': 300}
                    candidate = inverse_color(request, document)
                    record = candidate['cmyk_result']
                    percentages = np.asarray(record['cmyk'], dtype=float)
                    ink = np.rint(percentages * 255 / 100).astype(int)
                    predicted, _, _ = Predictor(document, strength, mode).forward([ink], 'CMYK')
                    de = float(np.linalg.norm(rgb_to_lab(predicted[0]) - rgb_to_lab(np.asarray(target_rgb))))
                    expected_profile = 'GRACoL2013_CRPC6.icc' if mode == 'photo' else 'CoatedFOGRA39.icc'
                    need(candidate['model_mode'] == mode and candidate['strength'] == strength, 'Recommendation mode or strength changed.')
                    need(candidate['input_cmyk_profile'] == expected_profile, 'Recommendation CMYK profile contract changed.')
                    need(predicted[0].tolist() == record['predicted_rgb'], 'Displayed CMYK recommendation does not reproduce its prediction with the same mode/strength.')
                    need(round(de, 2) == record['delta_e76'], 'Re-entered recommendation residual differs from the reported Delta E 76.')
                    need(int(ink.sum()) <= 765 and float(percentages.sum()) <= 300.000001, 'CMYK recommendation exceeds the 300% ink limit.')
                    rows.append({'mode': mode, 'strength': strength, 'target_rgb': target_rgb, 'input_profile': expected_profile,
                                 'cmyk_percent': percentages.tolist(), 'reentered_cmyk_8bit': ink.tolist(),
                                 'predicted_rgb': predicted[0].tolist(), 'delta_e76': round(de,2),
                                 'quantized_tac_percent': float(ink.sum()) * 100 / 255})
                return {'cases': rows}

            check('delivered_pdf_source_13_anchors', delivered_check)
            check('equivalent_fogra_device_cmyk_6_colors', equivalent_check)
            check('explicit_and_mixed_icc_preserved', explicit_and_mixed_check)
            check('recommended_cmyk_same_mode_strength', inverse_check)

        # Confirm that verification did not change its baseline inputs either.
        check('original_inputs_unchanged_after_tests', preservation_check)
        result['all_pass'] = len(result['tests']) == 8 and all(item['pass'] for item in result['tests'].values())
        result['release_gate_eligible'] = result['all_pass'] and not args.native_gs and os.name == 'nt'
    except Exception as exc:
        result['fatal_error'] = str(exc)
        result['fatal_traceback'] = traceback.format_exc()
    finally:
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps({'all_pass': result['all_pass'], 'release_gate_eligible': result['release_gate_eligible'],
                          'output': str(args.output), 'elapsed_seconds': result['elapsed_seconds']}), flush=True)
    return 0 if result['all_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
