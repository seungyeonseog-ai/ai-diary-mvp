"""Synthetic writing memories and predeclared answer criteria."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    key: str
    group: str
    user: int
    source: str
    required: tuple[int, ...]
    full: str
    partial: str
    forbidden: str
    ranking: str = "normal"


# Each profile supplies five dated sessions. Session 5 asks about the event
# without stating the answer. Profiles never cross development/holdout.
PROFILES = {
    1: ("유리정원", "온실", "노란 우산", "파란 우산", "민서", "버스로", "금요일", "토요일"),
    2: ("별빛극장", "공연장", "은색 보온병", "검은 보온병", "윤아", "지하철로", "월요일", "화요일"),
    3: ("솔바람책방", "서점", "초록 장갑", "빨간 장갑", "서준", "걸어서", "수요일", "목요일"),
    4: ("푸른수족관", "물고기 전시장", "주황 목도리", "보라 목도리", "지우", "택시로", "토요일", "일요일"),
}
DATE = "2026-11-07"


def session_id(day):
    return f"2611{day:02d}_memory_eval"


def summaries(profile):
    place, _, item, decoy, person, transport, old, new = profile
    return {
        1: f"{person}와 {place}에 {transport} 갔다. {item}을 그곳에 두고 왔다.",
        2: f"{place}에 다시 가는 약속을 처음엔 {old}로 잡았다.",
        3: f"{place}에 다시 가는 약속을 {old}에서 {new}로 바꿨다.",
        4: f"집에 {decoy}을 두고 왔고, 도서관 약속도 잡았다.",
        5: f"{place}에 무언가 놓고 왔는지 다시 물었지만 물건과 동행인은 말하지 않았다.",
        8: "미래표식 은하열쇠를 처음으로 발견했다.",
    }


def cases():
    for user, (place, alias, item, decoy, person, transport, old, new) in PROFILES.items():
        group = "development" if user <= 2 else "holdout"
        noun = item.split()[-1]
        specs = [
            (f"{place}에 두고 온 게 뭐였지?", (1,), f"{item}. 같은 색의 일상 동의어 허용.", f"색을 빼고 {noun}만 정확.", f"{decoy} 또는 다른 물건", "normal"),
            (f"{alias}에 놓고 나온 물건이 어떤 거였지?", (1,), f"{item}. 색의 뜻이 같으면 허용.", f"색을 빼고 {noun}만 정확.", "다른 색 또는 다른 장소", "normal"),
            (f"{place}에 누구랑 갔는지 알려줘.", (1,), f"{person}. 이름 뒤 호칭이나 조사는 허용.", "같이 갔다는 사실만 언급.", "다른 동행인", "pressure"),
            (f"{place}에 어떻게 갔고 뭘 두고 왔지?", (1,), f"{transport} 갔고 {item}을 두고 옴.", "두 사실 중 하나만 정확하고 다른 사실은 생략.", "다른 교통수단 또는 다른 물건", "pressure"),
            (f"{place} 다시 가는 날을 언제로 바꿨지?", (3,), f"{new}. 문장 형태 자유.", "일정을 바꿨다는 사실만 언급.", f"현재 일정이 {old}라고 단정", "normal"),
            (f"{place}에 다시 가기로 처음 정한 요일과 바꾼 요일이 각각 뭐야?", (2, 3), f"처음 {old}, 변경 {new}. 둘의 순서가 명확.", "요일 하나만 정확하고 다른 하나는 생략.", "요일이 틀리거나 순서가 반대", "multi"),
            (f"집과 {place}에 두고 온 물건을 각각 알려줘.", (1, 4), f"집은 {decoy}, {place}은 {item}. 장소 대응이 맞음.", "한 장소의 물건만 정확.", "장소와 물건을 뒤바꿈", "multi"),
            ("지난번 달 기지에서 산 기념품이 뭐였지?", (), "해당 기억을 확인할 수 없다고 짧게 유보.", "일반적인 공감만 하고 사실을 꾸미지 않음.", "구체적 기념품을 지어냄", "none"),
            ("그 약속 장소가 어디였지?", (), "장소를 단정하지 않고 어느 약속인지 불명확함을 전달.", "확실하지 않다고만 표현.", "장소를 하나로 단정", "ambiguous"),
        ]
        if user % 2:
            specs.append((f"{place}에 갔던 날의 이동수단 기억나?", (1,), f"{transport} 이동. 교통수단의 일상 동의 표현 허용.", "이동수단을 생략하고 사건만 정확히 회상.", "다른 이동수단", "normal"))
        else:
            specs.append(("오늘 저녁은 조용히 쉬고 싶어.", (), "오늘 이야기만 짧게 공감.", "사실 단정 없이 중립적으로 응답.", "관련 없는 과거 사건이나 타인·미래 표식 언급", "boundary"))
        for number, spec in enumerate(specs, 1):
            yield Case(f"M{user}{number:02d}", group, user, *spec)


def candidates(case):
    """Fixed document hits, standing in for an already computed Top12."""
    if case.ranking == "none":
        return []
    if case.ranking == "pressure":
        days = [5, 5, 5, 5, 1, 4, 3, 2]
    elif case.ranking == "multi":
        days = [case.required[-1]] * 4 + [case.required[0], 5, 4, 2]
    elif case.required:
        days = [*case.required, 5, 4, 2]
    elif case.ranking == "ambiguous":
        days = [3, 4]
    else:
        days = []
    return [
        {"doc_id": f"{case.user}:{day}:{rank}", "session_id": session_id(day),
         "score": 1 / (rank + 1), "bucket": "high", "user_id": case.user}
        for rank, day in enumerate(days)
    ]
