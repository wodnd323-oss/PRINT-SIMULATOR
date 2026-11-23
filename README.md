# HARDYS 인쇄색 시뮬레이터 V11.2

Windows용 인쇄색 미리보기와 목표색·그라데이션 역산 도구입니다. 디자이너 전달본 케이스7 PDF와 기존 실물 사진의 같은 위치를 비교해 학습한 사진 경향과 FOGRA39 표준 프루프를 구분합니다.

## 다운로드와 설치

[V11.2 릴리스](https://github.com/wodnd323-oss/PRINT-SIMULATOR/releases/tag/v11.2)에서 설치 파일을 받습니다. 릴리스는 별도 Windows 환경의 번들 Python·Ghostscript 9.50 검증을 통과한 뒤 공개합니다.

- **신규 설치:** `HARDYS_PrintSimulator_v11_2_Full_Install.zip`을 전부 풀고 `START.cmd`를 실행합니다.
- **기존 V11 또는 V11.1:** 프로그램 종료 → 기존 설치 폴더 전체 백업 → `HARDYS_PrintSimulator_v11_2_Update.zip`의 `UPDATE_FILES` 안 내용을 `START.cmd`가 있는 폴더에 덮어쓰기 → 다시 실행합니다.
- 패치는 사용자 보정 상태, 업로드·내보내기 자료, Windows 또는 모니터 색 설정을 변경하지 않습니다.
- [V11.1 릴리스](https://github.com/wodnd323-oss/PRINT-SIMULATOR/releases/tag/v11.1)와 기존 검증 기록은 보존합니다.

## V11.2 변경 내용

1. 늦게 도착한 색상 조회 응답이 최신 입력을 덮어쓰는 문제를 수정했습니다.
2. 직접 색상 비교의 사진/ICC 모드와 역산 추천의 동일 조건 RGB·CMYK 재확인을 추가했습니다.
3. 그라데이션의 정확한 CSS 각도와 좌표 기준을 표시하고, 2색·3색 선택을 표·미리보기·통계·PNG 저장·큰 비교에 일관되게 적용합니다.
4. 결과별로 사진 기준색 근처·전환·외삽을 표시합니다. 중성·저채도는 따로 세며, 이 비율은 정확도나 성공확률이 아닙니다.
5. 강한 TAC 제한에서 유효한 그라데이션 후보를 놓치는 탐색을 개선하고 전체 양자화 경로의 잉크량을 확인합니다.
6. 헤더만 다른 동등 FOGRA OutputIntent의 DeviceCMYK 표준 경로를 보완했습니다. 원본·사진 경로·명시적 객체 ICC를 유지하며, 명시적 ICCBased의 남은 경계는 경고합니다.

자세한 내용은 [업데이트 설명](source/HARDYS_V11_2_UPDATE_NOTES.txt)과 설치본 도움말의 `web/update_v11_2.html`에서 확인합니다. 기존 계산 근거인 `web/calculation_review.html`도 그대로 있습니다.

## 계산 범위와 한계

사진 경로는 원본 ICC 해석 → sRGB → D65 Lab → 사진 경향과 기준색 근처 잔차 보정 → sRGB입니다. 표준 경로는 원본 ICC → FOGRA39 상대비색+BPC → sRGB 상대비색이며 마지막 변환의 BPC는 끕니다. 표준 프루프 위에 사진 보정을 중복 적용하지 않습니다.

사진 모델 수식·13개 기준 영역·10개 고유 입력색·GRACoL/FOGRA 프로파일은 V11.1과 같습니다. 같은 사진의 학습 평균 ΔE76은 1.58이고, 같은 입력색을 통째로 제외하면 평균 5.81·최대 19.91입니다. 새로운 색 계열은 외삽이며, 실제 인쇄 교정·측색·인쇄소 RIP 검증을 대신하지 않습니다.

## 검증과 재현 빌드

- [V11.2 검증 요약](verification/2026-11-23-v11.2.json): HTTP 69개, 색상 UI 함수 9개, 그라데이션 UI 함수 20개, 역산·지원범위 88개, PDF ICC 7그룹을 점검했습니다.
- 설치본의 `verification_results/update_v11_2`에는 세부 결과가 있습니다. 브라우저 시작이 실행 환경에서 차단되어 실제 화면의 시각 검사는 완료하지 못했습니다.
- 릴리스의 `WINDOWS_VERIFICATION.json`은 별도 Windows에서 실제 번들 Python·Ghostscript 9.50으로 검사한 결과입니다. 사용자 PC 설치 확인과는 별개입니다.
- `BUILD_VERIFICATION.json`은 전체본의 모든 파일과 패치의 대응 파일을 대조한 기록입니다. `PUBLIC_DOWNLOAD_VERIFICATION.json`은 게시한 ZIP을 다시 받아 해시를 확인한 기록입니다.

저장소의 `distribution/parts/installer.*`는 보존한 V11.1 전체본 조각입니다. V11.2는 이 원본과 해시가 고정된 변경 파일을 합쳐 재현합니다. Python 3가 있는 환경에서 저장소 루트에서 실행합니다.

```sh
python packaging/build_release.py
```

`release/`에 V11.2 전체본·패치·검증 기록이 생성됩니다. 기대 SHA256은 [distribution/SHA256SUMS-v11.2](distribution/SHA256SUMS-v11.2)에 있습니다. Windows/Linux 줄바꿈 변환을 막고, 원본 ZIP·변경 파일·최종 ZIP을 각각 검증합니다. 기존 V11.1 패치도 포함하므로 V11에서의 누적 업데이트가 가능합니다.
