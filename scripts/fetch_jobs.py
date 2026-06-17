#!/usr/bin/env python3
"""
워크넷 채용공고 수집 스크립트

사전 준비:
  1. 워크넷 OpenAPI 신청: https://www.work.go.kr/opi/opi/main/main.do
  2. 발급받은 authKey를 GitHub Secret 'WORKNET_API_KEY' 에 등록
  3. GitHub Actions가 매일 이 스크립트를 실행하여 data/jobs.json 을 갱신합니다.

지역코드 참고 (워크넷 OpenAPI 문서 기준):
  서울특별시 강남구 : 101270
  서울특별시 서초구 : 101280
  경기도 성남시     : 102290
  경기도 용인시     : 102310  (기흥구/수지구 포함)
  경기도 수원시     : 102090
"""

import os
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    raise SystemExit("requests 패키지가 필요합니다: pip install requests")

# ── 설정 ──────────────────────────────────────────────────────────────────────
WORKNET_API_KEY = os.environ.get("WORKNET_API_KEY", "")
BASE_URL = "https://www.work.go.kr/opi/opi/opia/wantListOpi.do"

JOB_KEYWORDS = [
    "그래픽디자이너",
    "브랜드디자이너",
    "콘텐츠디자이너",
]

REGION_MAP = {
    "서울 강남구": "101270",
    "서울 서초구": "101280",
    "경기 성남시": "102290",
    "경기 용인시": "102310",
    "경기 수원시": "102090",
}

# 용인시 필터링을 위한 세부 키워드 (기흥구·수지구)
YONGIN_SUBDISTRICTS = ["기흥", "수지"]


# ── API 호출 ──────────────────────────────────────────────────────────────────
def fetch_from_worknet(keyword: str, region_code: str, region_name: str) -> list:
    """워크넷 API에서 채용공고 목록을 가져온다."""
    params = {
        "authKey": WORKNET_API_KEY,
        "callTp": "L",
        "returnType": "XML",
        "startPage": "1",
        "display": "100",
        "keyword": keyword,
        "regionCd": region_code,
    }

    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [오류] {keyword} / {region_name}: {e}")
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"  [XML 파싱 오류] {keyword} / {region_name}: {e}")
        return []

    jobs = []
    # 워크넷 API 응답 필드명 (공식 문서 기준)
    for item in root.findall(".//WANT"):
        job_id = item.findtext("WANTEDAUTHNO", "").strip()
        location = item.findtext("WORKREGION", region_name).strip()

        # 용인시의 경우 기흥구·수지구만 포함
        if region_code == "102310":
            if not any(sub in location for sub in YONGIN_SUBDISTRICTS):
                continue

        if not job_id:
            continue

        jobs.append({
            "id": job_id,
            "title": item.findtext("WANTEDTITLE", "").strip(),
            "company": item.findtext("CMPNYNAME", "").strip(),
            "location": location,
            "region": region_name,
            "keyword": keyword,
            "salary": item.findtext("SALARYTYPENM", "").strip(),
            "posted": item.findtext("OPENINGDATE", "").strip(),
            "deadline": item.findtext("CLOSINGDATE", "").strip(),
            "source": "워크넷",
            "url": (
                "https://www.work.go.kr/empInfo/empInfoSrch/detail/"
                f"empDetailAuthView.do?wantedAuthNo={job_id}"
            ),
        })

    print(f"  {keyword} / {region_name}: {len(jobs)}건")
    return jobs


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    if not WORKNET_API_KEY:
        print("[경고] WORKNET_API_KEY 환경변수가 설정되지 않았습니다.")
        print("       GitHub Secret 'WORKNET_API_KEY' 를 등록해주세요.")
        return

    all_jobs: list = []
    seen_ids: set = set()

    for keyword in JOB_KEYWORDS:
        for region_name, region_code in REGION_MAP.items():
            jobs = fetch_from_worknet(keyword, region_code, region_name)
            for job in jobs:
                if job["id"] not in seen_ids:
                    seen_ids.add(job["id"])
                    all_jobs.append(job)
            time.sleep(0.3)  # API 서버 부하 방지

    # 날짜 기준 내림차순 정렬
    all_jobs.sort(key=lambda j: j.get("posted", ""), reverse=True)

    kst = timezone(timedelta(hours=9))
    output = {
        "updated_at": datetime.now(kst).strftime("%Y-%m-%d %H:%M"),
        "total": len(all_jobs),
        "jobs": all_jobs,
    }

    os.makedirs("data", exist_ok=True)
    with open("data/jobs.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n완료: 총 {len(all_jobs)}건 저장 → data/jobs.json")


if __name__ == "__main__":
    main()
