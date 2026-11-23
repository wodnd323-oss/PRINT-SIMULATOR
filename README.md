# HARDYS 인쇄색 시뮬레이터 V11.1

Windows용 인쇄색 미리보기와 목표색 역산 도구입니다. 사진으로 추정한 인쇄 경향과 FOGRA39 표준 프루프를 비교합니다.

[배포 파일](https://github.com/wodnd323-oss/PRINT-SIMULATOR/releases/tag/v11.1)에서 신규 설치는 Full_Install.zip, 기존 V11 업데이트는 Update.zip을 선택하세요. 신규 설치는 ZIP을 전부 풀고 START.cmd를 실행합니다. 설치본에 포함된 web/calculation_review.html에서 계산 근거를 볼 수 있습니다.

저장소 자체에서도 전체 설치 ZIP을 복원할 수 있습니다. 저장소를 내려받은 뒤 Windows PowerShell에서 아래 명령을 실행하세요.

```powershell
cd distribution
$stream = [IO.File]::Create((Join-Path $PWD 'HARDYS_PrintSimulator_v11_1_Full_Install.zip'))
try {
    Get-ChildItem parts/installer.* | Sort-Object Name | ForEach-Object {
        $part = [IO.File]::OpenRead($_.FullName)
        try { $part.CopyTo($stream) } finally { $part.Dispose() }
    }
} finally { $stream.Dispose() }
Get-FileHash HARDYS_PrintSimulator_v11_1_Full_Install.zip
```

SHA256 목록은 [distribution/SHA256SUMS](distribution/SHA256SUMS)에 있습니다. source 폴더에는 계산 및 화면 소스가 있습니다. 런타임, 인쇄 프로파일, 기준 PDF와 사진은 전체 설치 ZIP에 포함됩니다.

배포 기준 사진의 13개 표본을 학습한 평균 색차는 ΔE76 1.58이고, 같은 입력색을 전부 제외한 검사에서는 평균 5.81, 최대 19.91입니다. 새로운 색 계열의 실물 정확도에는 별도 인쇄 교정이 필요합니다.
