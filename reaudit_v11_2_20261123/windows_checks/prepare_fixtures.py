"""Recreate the exact three Linux audit fixtures from compact byte templates.

The unused-ICC PDF contains the unchanged GRACoL profile already shipped in the
verified public release. Store only its PDF prefix/suffix in this audit branch;
verify the profile and each complete fixture SHA256 before using the files.
No application files are changed. Existing different fixture bytes are rejected.
"""
import base64, hashlib, json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
APP=ROOT/'released_app'
OUT=ROOT/'proof_inputs/inputs'
RECORDS={'gray16_icc_linear.png': {'sha256': '74a4333cb9bb189ee3697e92fdee953880e6f3a7d5310340ac0fa18d81c3d523', 'base64': 'iVBORw0KGgoAAAANSUhEUgAAAAwAAAAIEAAAAAC4H51uAAAA2mlDQ1BhdWRpdAAAeJxjYGCMyUnOLWZxYGDIzSspcg9yjIyIjFJgf8XAzSDOwMLAzKCemFxc4BgQ4MOAE3y7xsAIoi/rgszCrQ4rYElJLU4G0luA2Cy5oKgESL8BYp/ykgIgm9ECyBbJDglyBrJBbhDIzSlNhuoF2cqTmhcaDKSlgFiGIZ2hiCGRoZJBgSGJoZQhkyGHoYRBF0jnAf2HXZ8BWJ8fQz5QTzKQLADqLgLqSGfIAOrVAYqWMhQzpALpNKB4KhDmMFSCwgjq9ztQv1sVJBYlwn0FFAMA5iky3cfgWnsAAAAjSURBVHicY2BgYGBksGeoZ2hgaGT4z8jAyMgCZP7/zzC0JADCoSohSJ10swAAAABJRU5ErkJggg=='}, 'unprofiled_cmyk_no_resource.pdf': {'sha256': '4069d4f018bd64592395bee73c067903587c5380d254e18331372041008ba5da', 'base64': 'JVBERi0xLjMKJeLjz9MKMSAwIG9iago8PAovUHJvZHVjZXIgKHB5cGRmKQo+PgplbmRvYmoKMiAwIG9iago8PAovVHlwZSAvUGFnZXMKL0NvdW50IDEKL0tpZHMgWyA0IDAgUiBdCj4+CmVuZG9iagozIDAgb2JqCjw8Ci9UeXBlIC9DYXRhbG9nCi9QYWdlcyAyIDAgUgo+PgplbmRvYmoKNCAwIG9iago8PAovVHlwZSAvUGFnZQovUmVzb3VyY2VzIDw8Cj4+Ci9NZWRpYUJveCBbIDAuMCAwLjAgMTYwIDMyIF0KL1BhcmVudCAyIDAgUgovQ29udGVudHMgNSAwIFIKPj4KZW5kb2JqCjUgMCBvYmoKPDwKL0xlbmd0aCA0NzUKPj4Kc3RyZWFtCi9EZXZpY2VDTVlLIGNzIDAuMDAwMDAwMDAwMDAwIDEuMDAwMDAwMDAwMDAwIDAuMDAwMDAwMDAwMDAwIDAuMDAwMDAwMDAwMDAwIHNjbiAwIDAgMzIgMzIgcmUgZgovRGV2aWNlQ01ZSyBjcyAwLjAwMDAwMDAwMDAwMCAwLjAwMDAwMDAwMDAwMCAwLjAwMDAwMDAwMDAwMCAxLjAwMDAwMDAwMDAwMCBzY24gMzIgMCAzMiAzMiByZSBmCi9EZXZpY2VDTVlLIGNzIDAuMzkyMTU2ODYyNzQ1IDAuMDc4NDMxMzcyNTQ5IDAuMDAwMDAwMDAwMDAwIDAuMTU2ODYyNzQ1MDk4IHNjbiA2NCAwIDMyIDMyIHJlIGYKL0RldmljZUNNWUsgY3MgMC4wMDAwMDAwMDAwMDAgMC4wMDAwMDAwMDAwMDAgMC4wMDAwMDAwMDAwMDAgMC4wMDAwMDAwMDAwMDAgc2NuIDk2IDAgMzIgMzIgcmUgZgovRGV2aWNlQ01ZSyBjcyAxLjAwMDAwMDAwMDAwMCAxLjAwMDAwMDAwMDAwMCAxLjAwMDAwMDAwMDAwMCAxLjAwMDAwMDAwMDAwMCBzY24gMTI4IDAgMzIgMzIgcmUgZgoKZW5kc3RyZWFtCmVuZG9iagp4cmVmCjAgNgowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMTUgMDAwMDAgbiAKMDAwMDAwMDA1NCAwMDAwMCBuIAowMDAwMDAwMTEzIDAwMDAwIG4gCjAwMDAwMDAxNjIgMDAwMDAgbiAKMDAwMDAwMDI3MSAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9TaXplIDYKL1Jvb3QgMyAwIFIKL0luZm8gMSAwIFIKPj4Kc3RhcnR4cmVmCjc5NwolJUVPRgo='}, 'unprofiled_cmyk_unused_gracol_resource.pdf': {'sha256': '2a67614d6e55b9c882d2bb17dcd9dff9ff7229dc030bdfb20ee07933f05a9efa', 'prefix_base64': 'JVBERi0xLjMKJeLjz9MKMSAwIG9iago8PAovUHJvZHVjZXIgKHB5cGRmKQo+PgplbmRvYmoKMiAwIG9iago8PAovVHlwZSAvUGFnZXMKL0NvdW50IDEKL0tpZHMgWyA0IDAgUiBdCj4+CmVuZG9iagozIDAgb2JqCjw8Ci9UeXBlIC9DYXRhbG9nCi9QYWdlcyAyIDAgUgo+PgplbmRvYmoKNCAwIG9iago8PAovVHlwZSAvUGFnZQovUmVzb3VyY2VzIDw8Ci9Db2xvclNwYWNlIDw8Ci9VbnVzZWQgWyAvSUNDQmFzZWQgNSAwIFIgXQo+Pgo+PgovTWVkaWFCb3ggWyAwLjAgMC4wIDE2MCAzMiBdCi9QYXJlbnQgMiAwIFIKL0NvbnRlbnRzIDYgMCBSCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9OIDQKL0xlbmd0aCAzNDYyMzA4Cj4+CnN0cmVhbQo=', 'suffix_base64': 'CmVuZHN0cmVhbQplbmRvYmoKNiAwIG9iago8PAovTGVuZ3RoIDQ3NQo+PgpzdHJlYW0KL0RldmljZUNNWUsgY3MgMC4wMDAwMDAwMDAwMDAgMS4wMDAwMDAwMDAwMDAgMC4wMDAwMDAwMDAwMDAgMC4wMDAwMDAwMDAwMDAgc2NuIDAgMCAzMiAzMiByZSBmCi9EZXZpY2VDTVlLIGNzIDAuMDAwMDAwMDAwMDAwIDAuMDAwMDAwMDAwMDAwIDAuMDAwMDAwMDAwMDAwIDEuMDAwMDAwMDAwMDAwIHNjbiAzMiAwIDMyIDMyIHJlIGYKL0RldmljZUNNWUsgY3MgMC4zOTIxNTY4NjI3NDUgMC4wNzg0MzEzNzI1NDkgMC4wMDAwMDAwMDAwMDAgMC4xNTY4NjI3NDUwOTggc2NuIDY0IDAgMzIgMzIgcmUgZgovRGV2aWNlQ01ZSyBjcyAwLjAwMDAwMDAwMDAwMCAwLjAwMDAwMDAwMDAwMCAwLjAwMDAwMDAwMDAwMCAwLjAwMDAwMDAwMDAwMCBzY24gOTYgMCAzMiAzMiByZSBmCi9EZXZpY2VDTVlLIGNzIDEuMDAwMDAwMDAwMDAwIDEuMDAwMDAwMDAwMDAwIDEuMDAwMDAwMDAwMDAwIDEuMDAwMDAwMDAwMDAwIHNjbiAxMjggMCAzMiAzMiByZSBmCgplbmRzdHJlYW0KZW5kb2JqCnhyZWYKMCA3CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAxNSAwMDAwMCBuIAowMDAwMDAwMDU0IDAwMDAwIG4gCjAwMDAwMDAxMTMgMDAwMDAgbiAKMDAwMDAwMDE2MiAwMDAwMCBuIAowMDAwMDAwMzE3IDAwMDAwIG4gCjAwMDM0NjI2ODUgMDAwMDAgbiAKdHJhaWxlcgo8PAovU2l6ZSA3Ci9Sb290IDMgMCBSCi9JbmZvIDEgMCBSCj4+CnN0YXJ0eHJlZgozNDYzMjExCiUlRU9GCg==', 'embedded_profile': 'icc/GRACoL2013_CRPC6.icc', 'embedded_profile_sha256': '4ebbfad6bc9cfc033fdafdd8ac5df8159208932cb16d9a6596d349ae7ab50443'}}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    receipt={}
    for name,record in RECORDS.items():
        if 'base64' in record:
            data=base64.b64decode(record['base64'])
        else:
            profile=(APP/record['embedded_profile']).read_bytes()
            if hashlib.sha256(profile).hexdigest()!=record['embedded_profile_sha256']:
                raise ValueError('Public-release ICC hash differs from the reviewed fixture profile.')
            data=base64.b64decode(record['prefix_base64'])+profile+base64.b64decode(record['suffix_base64'])
        actual=hashlib.sha256(data).hexdigest()
        if actual!=record['sha256']:raise ValueError('Fixture reconstruction hash mismatch: '+name)
        path=OUT/name
        if path.exists():
            if path.read_bytes()!=data:raise ValueError('Refusing to overwrite different existing fixture: '+name)
        else:path.write_bytes(data)
        receipt[name]={'sha256':actual,'bytes':len(data),'verified':True}
    result=HERE/'results'
    result.mkdir(parents=True,exist_ok=True)
    (result/'fixture_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'fixture_reconstruction_verified':True,'files':receipt}))

if __name__=='__main__':main()
