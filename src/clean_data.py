# -*- coding: utf-8 -*-
"""
fss_dispute_cases.csv 전처리 스크립트
- 노이즈(제목반복/hwp첨부안내/이미지변환문구/담당부서안내) 제거
- 섹션(▣ 민원내용 / 쟁점 / 처리결과 / 소비자유의사항) 파싱
- 줄바꿈 위주 텍스트를 자연스러운 문단으로 정규화
- 결과: cleaned_cases.csv (RAG 임베딩용 최종 텍스트 포함)
"""
import csv
import re
import json

SRC = "/home/opc/fss_dispute_cases.csv"
OUT = "/home/opc/cleaned_cases.csv"

SECTION_NAMES = ["민원내용", "쟁점", "처리결과", "조정결과", "심사결과", "소비자유의사항", "결정이유"]
END_MARKERS = ["목록", "정보관리 담당부서 안내", "담당부서"]

# 공백·개행 정규화 및 크롤링 잔여 노이즈 제거
def normalize_ws(text: str) -> str:
    """한 글자씩 개행된 텍스트를 자연스러운 문장으로 복원"""
    # 연속 개행/공백을 단일 공백으로
    text = re.sub(r'[\r\n]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    # "숫자\n숫자" 형태로 쪼개진 금액 표기 등은 이미 공백 결합됨. 문장부호 앞 공백 정리
    text = re.sub(r'\s+([.,);:%])', r'\1', text)
    text = re.sub(r'\(\s+', '(', text)
    return text.strip()

# 본문에서 '민원내용/쟁점/처리결과/소비자유의사항' 섹션을 라벨 기준으로 분리
def parse_sections(raw: str):
    """▣ 마커 기준으로 섹션 분리 (원본 추출 과정에서 단어 사이 개행이 들어가는 경우가 있어
    섹션명 문자 사이에 임의 공백/개행이 끼어도 매칭되도록 문자 단위로 유연하게 패턴 구성)"""
    flexible_names = [r'\s*'.join(list(name)) for name in SECTION_NAMES]
    pattern = re.compile(r'▣\s*(' + '|'.join(flexible_names) + r')\s*')
    matches = list(pattern.finditer(raw))
    sections = {}
    for i, m in enumerate(matches):
        name = re.sub(r'\s+', '', m.group(1))  # 매칭된 텍스트의 공백 제거 -> 표준 섹션명으로 정규화
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(raw)
        content = raw[start:end]
        # 종료 마커(목록/담당부서안내) 이후 잘라내기
        for em in END_MARKERS:
            idx = content.find(em)
            if idx != -1:
                content = content[:idx]
        sections[name] = normalize_ws(content)
    return sections

# 임베딩 입력용 통합 텍스트 합성: 제목+유형+쟁점+처리결과를 하나의 case_text로
def build_case_text(row, sections):
    """RAG 임베딩용 최종 텍스트 조립: 제목 + 유형 + 민원내용 + 쟁점 + 처리결과"""
    parts = [f"[{row['유형']}] {row['제목']}"]
    if sections.get("민원내용"):
        parts.append(f"민원내용: {sections['민원내용']}")
    if sections.get("쟁점"):
        parts.append(f"쟁점: {sections['쟁점']}")
    처리결과 = sections.get("처리결과") or sections.get("조정결과") or sections.get("심사결과")
    if 처리결과:
        parts.append(f"처리결과: {처리결과}")
    if not sections.get("민원내용") and not 처리결과:
        # 마커가 아예 없는 2건 등: fallback으로 제목/유형만 사용
        parts.append("(상세 본문 미확보 - 제목/유형 기준)")
    return "\n".join(parts)

def main():
    """전처리 파이프라인: 원천 CSV → 섹션 파싱·정규화 → case_id(FSS-XXXX) 부여 →
    임베딩용 case_text 합성 → cleaned_cases.csv 저장."""
    with open(SRC, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    out_rows = []
    no_section_count = 0
    for row in rows:
        sections = parse_sections(row["본문"])
        if not sections:
            no_section_count += 1
        case_text = build_case_text(row, sections)
        out_rows.append({
            "case_id": f"FSS-{int(row['번호']):04d}",
            "권역": row["권역"],
            "유형": row["유형"],
            "제목": row["제목"],
            "등록일": row["등록일"],
            "민원내용": sections.get("민원내용", ""),
            "쟁점": sections.get("쟁점", ""),
            "처리결과": sections.get("처리결과") or sections.get("조정결과") or sections.get("심사결과", ""),
            "소비자유의사항": sections.get("소비자유의사항", ""),
            "case_text": case_text,
            "상세URL": row["상세URL"],
        })

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"총 {len(out_rows)}건 처리 완료 -> {OUT}")
    print(f"섹션 파싱 실패(마커 없음): {no_section_count}건")
    lens = [len(r["case_text"]) for r in out_rows]
    print(f"case_text 길이 - min:{min(lens)} max:{max(lens)} avg:{sum(lens)//len(lens)}")

if __name__ == "__main__":
    main()
