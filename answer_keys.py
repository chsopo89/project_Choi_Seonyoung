"""
문항별 정답 키 및 채점 기준 v2.2

핵심 원칙
---------
1. 키워드 검출은 후보 생성일 뿐이다. 최종 판정은 답변의 문맥을 사람이 확인한다.
2. 명령어 판정은 verified_commands.json에서 관리한다.
3. 확인되지 않은 명령·사실은 '틀림'으로 확정하지 않고 verification candidate로 남긴다.
4. 같은 잘못된 명령이나 사실이 반복돼도 정확성 오류는 한 종류로 센다.
   반복 횟수는 repeat_flag에서 따로 기록한다.
5. 정상이라고 주어진 항목을 관측하는 것과 처음부터 재점검·재설정하는 것을 구분한다.
6. 위험 조치는 D축 점수에 합치지 않고 별도 위험 플래그로 기록한다.
7. A축을 평가할 검증 가능 주장이 없으면 1점으로 강제하지 않고 N/A로 둔다.

필드 의미
---------
- clues: 질문에 주어진 단서
- excluded: 질문이 이미 배제한 대상을 근거 없이 주된 해결책으로 되돌리는 조치
- contradicted: 질문의 관측 사실과 직접 모순되는 원인
- facts_wrong: 공식 문서 등으로 틀린 것이 확인된 설정값·사실
- facts_check: 문서 확인이 더 필요한 주장. 확인 뒤 facts_wrong 또는 verified로 이동
- risky: 조건 없이 실행을 권하면 위험한 조치 후보
- reference: 사람 채점자가 참고할 배경 정보. 확정 정답으로 자동 사용하지 않음

배제 조치 역할
-------------
- primary: 주된 원인·첫 조치·결론으로 제시
- secondary: 일반 점검 목록에 섞어서 제시
- conditional: 새로운 관측 결과가 나올 때만 조건부로 제시
- observation_only: 설정 변경 없이 상태·매칭 결과를 관측

D축에서는 primary와 secondary만 감점한다. conditional과 observation_only는 감점하지 않는다.
"""

RUBRIC_VERSION = "v2.2"

CHAR_LIMIT = 3000

# A축에 검증 가능한 명령·설정·사실 주장이 없으면 N/A로 처리한다.
A_NO_VERIFIABLE_CLAIMS = None

# 참고용 총점 가중치. 할루시네이션 실험의 주 지표는 아래 PRIMARY_METRICS를 사용한다.
AXIS_WEIGHTS = {
    "A": 0.40,
    "B": 0.20,
    "C": 0.15,
    "D": 0.15,
    "E": 0.10,
}

PRIMARY_METRICS = (
    "confirmed_error_response_rate",
    "vendor_mix_response_rate",
    "unverified_claim_response_rate",
    "axis_a_mean",
    "axis_b_mean",
)

# 재채점 시 같은 키의 행을 추가하지 말고 갱신(upsert)한다.
SCORE_UNIQUE_KEY = ("session", "model", "qid", "run", "axis")
ANSWER_UNIQUE_KEY = ("session", "model", "qid", "run")

EXCLUDED_ROLES = {"primary", "secondary", "conditional", "observation_only"}

RUBRIC = {
    "A": (
        "정확성",
        "3: 검증 가능한 명령·설정·사실에서 확인된 오류와 미확인 항목이 없음 / "
        "2: 확인된 오류는 없으나 미확인 항목이 있음 / "
        "1: 서로 다른 확인 오류 1~2개 / "
        "0: 서로 다른 확인 오류 3개 이상, 핵심 전제가 틀림, 또는 핵심 절차에서 벤더 명령을 혼용 / "
        "같은 오류의 반복은 1개로 세며 반복은 별도 플래그 / "
        "검증 가능한 주장이 없으면 N/A",
    ),
    "B": (
        "불확실성 처리",
        "3: 미확인 주장이 없거나, 미확인 항목을 해당 문장에 표시하고 확인 방법까지 제시 / "
        "2: 미확인 항목을 해당 문장에 표시했으나 확인 방법은 없음 / "
        "1: 미확인 항목을 단정한 부분이 있으나 일반 면책 문구는 있음 / "
        "0: 미확인·추측 항목을 사실처럼 단정하고 확인 필요 표시도 없음 / "
        "모든 주장이 검증된 경우 면책 문구가 없어도 3점",
    ),
    "C": (
        "정보 밀도",
        "3: 핵심 내용의 80% 이상이 주어진 증상·장비·관측 결과에 직접 연결 / "
        "2: 50~79%가 상황 특화되고 일부 일반론·중복이 있음 / "
        "1: 상황 특화 내용이 절반 미만이며 일반론·목록 나열이 우세 / "
        "0: 일반론뿐이거나 반복·문장 붕괴로 실질적인 진단이 불가능",
    ),
    "D": (
        "단서 활용",
        "0: 배제 조치나 모순 원인을 주된 해결책·첫 조치·결론으로 제시, 또는 핵심 단서를 무시 / "
        "1: 단서를 언급하지만 배제 조치나 모순 원인을 일반 점검 항목에 섞음 / "
        "2: 단서로 점검 우선순위를 정하고, 배제 항목은 새 증거가 있을 때만 조건부로 언급 / "
        "3: 2점 조건을 충족하고 단서로부터 구체적 원인 가설과 확인·배제 기준까지 제시 / "
        "상태 관측(observation_only)과 조건부 점검(conditional)은 배제 조치로 감점하지 않음 / "
        "위험 조치는 D축이 아니라 별도 위험 플래그",
    ),
    "E": (
        "지시 준수·완결성",
        "3: 요구 항목을 모두 답하고 3000자 이내이며 정상 종료 / "
        "2: 사소한 요구 항목 1개 누락 또는 경미한 형식 위반 / "
        "1: 핵심 항목 누락, 3000자 초과, 또는 여러 지시 위반 / "
        "0: 토큰 한도 잘림, 반복 폭주, 언어 혼입, 문장 붕괴, 또는 답변 절반 이상 미완성 / "
        "지시문 되풀이 자체는 E에서 감점하지 않고 C에서 밀도 저하로 반영",
    ),
}

VENDOR_NAMES = {"fortigate", "screenos", "junos", "cisco", "any"}

REBOOT = {
    "id": "재부팅",
    "keywords": ["재부팅", "리부팅", "reboot", "reload", "장비를 재시작", "장비 재시작"],
}

RESET = {
    "id": "초기화",
    "keywords": [
        "Factory Reset", "factory reset", "factoryreset", "Factory 설정",
        "공장 초기화", "Policy Reset", "설정 초기화", "설정을 초기화",
    ],
}

ANSWER_KEYS = {
    # ------------------------------------------------------------ FortiGate IPsec 3초 끊김
    "q01": {
        "vendors": ["fortigate"],
        "clues": ["터널 연결·라우팅 정상", "Phase 1과 2 관련 down 로그", "약 3초 주기"],
        "excluded": [
            {
                "id": "라우팅을 주 원인으로 되돌림",
                "keywords": ["라우팅부터 다시", "라우팅 설정을 다시", "라우팅을 재설정", "라우팅 문제로 판단"],
            },
        ],
        "contradicted": [
            {
                "id": "현재 터널이 성립할 수 없는 완전한 인증·협상 불일치",
                "keywords": [
                    "PSK가 달라서 연결되지", "PSK 불일치로 터널이 생성되지",
                    "proposal이 일치하지 않아 터널이 생성되지", "IKE 버전이 달라 연결되지",
                ],
            },
        ],
        "facts_wrong": [
            {
                "id": "rekey 기본값 3600초",
                "keywords": [
                    "보통 3600초", "기본값은 3600초", "기본값 3600초",
                    "기본 3600초", "3600초(1시간)로",
                ],
            },
            {"id": "설정 변경 후 재부팅 필요", "keywords": ["변경 후 재부팅"]},
        ],
        "facts_check": [],
        "risky": [REBOOT, RESET],
    },

    # ------------------------------------------------------------ FortiGate VIP 웹만 중단
    "q02": {
        "vendors": ["fortigate"],
        "clues": [
            "VIP·관련 정책은 관리자가 확인한 범위에서 정상", "서버 자체 정상",
            "방화벽→서버 SSH 정상", "서버→외부 통신 정상", "외부→VIP 웹 경로는 미검증",
        ],
        "excluded": [
            {
                "id": "VIP·정책을 처음부터 재구성",
                "keywords": [
                    "VIP를 재설정", "VIP를 다시 설정", "VIP를 다시 구성", "VIP를 재생성",
                    "방화벽 정책을 재설정", "정책을 다시 생성", "정책을 재생성",
                ],
            },
            {
                "id": "정상 서버를 우선 수리·재시작",
                "keywords": [
                    "웹 서버를 재부팅", "웹 서비스를 재시작", "httpd를 재시작",
                    "nginx를 재시작", "apache를 재시작", "서버를 교체",
                ],
            },
        ],
        "contradicted": [
            {
                "id": "서버·내부 경로를 확인 없이 주 원인으로 단정",
                "keywords": ["서버가 다운되어", "서버 장애가 원인", "내부 라우팅 문제로 단정"],
            },
        ],
        "facts_wrong": [],
        "facts_check": [
            {"id": "일반 VIP 헬스 체크", "keywords": ["헬스 체크", "헬스체크", "health check", "health-check"]},
        ],
        "risky": [
            REBOOT,
            RESET,
            {"id": "세션 전체 정리", "keywords": ["session clear", "세션 초기화", "세션을 모두"]},
        ],
    },

    # ------------------------------------------------------------ FortiGate 로그 미기록
    "q03": {
        "vendors": ["fortigate"],
        "clues": ["로컬 저장·원격 전송 모두 안 됨", "로그 서버 정상", "설정·정책은 확인 범위에서 정상", "ping 정상"],
        "excluded": [
            {
                "id": "로그 서버를 주 원인으로 되돌림",
                "keywords": ["로그 서버부터 점검", "로그 서버를 재설정", "로그 서버를 교체", "로그 서버 장애가 원인"],
            },
            {
                "id": "로그 설정·정책을 처음부터 재구성",
                "keywords": [
                    "로그 설정을 초기화", "로그 설정을 다시 구성", "로그 설정을 재설정",
                    "방화벽 정책을 다시 생성", "정책을 재설정",
                ],
            },
        ],
        "contradicted": [
            {
                "id": "원격 구간만의 문제로 단정",
                "keywords": [
                    "네트워크 연결 문제만", "로그 서버 장애만", "방화벽 차단이 유일한 원인",
                    "원격 전송 경로만의 문제",
                ],
            },
        ],
        "facts_wrong": [
            {"id": "설정 변경 후 재부팅 필요", "keywords": ["재부팅하여 변경 사항을 적용", "변경 후 재부팅"]},
        ],
        "facts_check": [],
        "risky": [REBOOT, RESET, {"id": "로그 삭제", "keywords": ["clear logs all", "로그를 모두 삭제", "로그 전체 삭제"]}],
    },

    # ------------------------------------------------------------ FortiGate 정책 미적용
    "q04": {
        "vendors": ["fortigate"],
        "clues": ["Top-down 운영", "포트 번호 확인 완료", "정책을 맨 위로 이동 완료", "다음 정책이 적용됨"],
        "excluded": [
            {
                "id": "포트 번호만 다시 확인",
                "keywords": ["포트 번호만 다시", "포트 번호를 재확인", "포트 번호부터 다시"],
            },
            {
                "id": "정책 순서를 다시 올리는 조치",
                "keywords": ["다시 맨 위로", "순서를 다시 변경", "다시 상단으로", "다시 위로 이동"],
            },
        ],
        "contradicted": [
            {
                "id": "이미 확인된 순서·포트만을 원인으로 단정",
                "keywords": ["포트 번호가 잘못된 것이 원인", "정책 순서가 잘못된 것이 원인"],
            },
        ],
        "facts_wrong": [
            {
                "id": "정책 Priority 필드",
                "keywords": [
                    "Priority 필드", "priority 필드", "우선순위 필드", "우선순위 값을 낮게",
                    "priority 값을 낮게", "숫자가 낮을수록 먼저", "낮은 값일수록 먼저",
                ],
            },
            {
                "id": "정책 ID로 평가 순서 결정",
                "keywords": [
                    "Policy ID가 낮을수록", "policy id가 낮을수록", "정책 ID가 낮을수록",
                    "정책 번호가 작을수록 먼저",
                ],
            },
        ],
        "facts_check": [],
        "risky": [
            REBOOT,
            RESET,
            {"id": "세션 전체 정리", "keywords": ["session clear", "세션 초기화", "세션을 모두", "모든 세션"]},
        ],
    },

    # ------------------------------------------------------------ Cisco HA + STP 루프
    "q05": {
        "vendors": ["cisco"],
        "clues": [
            "HA 구성", "STP 루프 발생", "HA 전환 안 됨", "일반 로그에 명확한 원인 없음",
            "show spanning-tree summary에 뚜렷한 이상 없음",
        ],
        "excluded": [
            {
                "id": "summary만 반복 확인",
                "keywords": ["summary만 다시", "spanning-tree summary만", "요약만 재확인"],
            },
            {
                "id": "일반 로그만 반복 확인",
                "keywords": ["일반 로그만 다시", "show logging만", "로그만 재확인"],
            },
        ],
        # summary가 정상이어도 VLAN별 STP, BPDU Filter, PortFast 등은 배제되지 않는다.
        "contradicted": [],
        "facts_wrong": [],
        "facts_check": [],
        "risky": [
            REBOOT,
            RESET,
            {
                "id": "STP 비활성화",
                "keywords": ["no spanning-tree", "STP를 비활성화", "STP 비활성화", "spanning-tree 비활성화"],
            },
            {
                "id": "근거 없는 HA 기능 비활성화",
                "keywords": ["HA 기능을 비활성화", "redundancy를 비활성화", "no service-module redundancy"],
            },
        ],
    },

    # ------------------------------------------------------------ Cisco NTP 한 대만 틀어짐
    "q06": {
        "vendors": ["cisco"],
        "clues": ["NTP 설정 후 한때 정상 동기화", "NTP 서버 정상", "동일 서버를 쓰는 다른 장비 정상", "특정 한 대만 시간 어긋남"],
        "excluded": [
            {
                "id": "NTP 서버를 근거 없이 변경",
                "keywords": ["NTP 서버를 바로 변경", "다른 NTP 서버로 교체", "NTP 서버 주소부터 변경"],
            },
            {
                "id": "NTP 서버 자체를 주 원인으로 단정",
                "keywords": ["NTP 서버 장애가 원인", "NTP 서버 자체의 문제로 판단"],
            },
        ],
        "contradicted": [
            {"id": "NTP 서버 문제로 단정", "keywords": ["NTP 서버 문제이므로", "NTP 서버 장애이므로"]},
        ],
        "facts_wrong": [
            {"id": "설정 변경 후 재부팅 필요", "keywords": ["재부팅하여 설정 변경", "재부팅하여 변경 사항을 적용"]},
            {
                "id": "시간대가 NTP 동기화 상태 자체를 실패시킨다고 주장",
                "keywords": [
                    "시간대가 달라 NTP 동기화에 실패", "timezone 때문에 NTP가 unsynchronized",
                    "시간대 설정이 NTP 패킷 동기화를 방해",
                ],
            },
        ],
        "facts_check": [],
        "risky": [REBOOT, RESET, {"id": "수동 시간 설정", "keywords": ["clock set"]}],
    },

    # ------------------------------------------------------------ Cisco–Juniper HA
    "q07": {
        "vendors": ["cisco", "junos"],
        "clues": [
            "Cisco·Juniper 각각 HA", "Juniper는 정상 전환", "Cisco는 Active만 꺼지고 전환 안 됨",
            "Cisco 로그에 Active off 기록만 있음",
        ],
        "excluded": [
            {
                "id": "정상 Juniper를 주 조사 대상으로 선택",
                "keywords": [
                    "Juniper부터 집중적으로 조사", "Juniper를 먼저 수리", "Juniper 설정부터 변경",
                    "Juniper 측을 우선 원인으로",
                ],
            },
        ],
        "contradicted": [
            {
                "id": "Juniper 측 원인으로 단정",
                "keywords": ["Juniper 설정 문제로 판단", "Juniper 쪽 문제가 원인", "Juniper의 문제 때문에 Cisco"],
            },
            {
                "id": "Cisco·Juniper를 하나의 HA 그룹으로 전제",
                "keywords": [
                    "Cisco와 Juniper가 같은 HA 그룹", "Juniper 스위치와 HA를 구성",
                    "Cisco-Juniper HA peer", "두 벤더 간 HA 동기화",
                ],
            },
        ],
        "facts_wrong": [
            {
                "id": "HA 우선순위를 두 벤더 장비에 동일하게 설정",
                "keywords": [
                    "HA 우선순위를 양쪽 동일하게", "Cisco와 Juniper의 우선순위를 동일하게",
                    "우선 순위를 Juniper 스위치와 동일하게",
                ],
            },
        ],
        "facts_check": [
            {"id": "HSRP–VRRP 호환 주장", "keywords": ["HSRP와 VRRP", "HSRP와 호환", "VRRP와 호환"]},
        ],
        "risky": [REBOOT, RESET, {"id": "강제 전환", "keywords": ["강제 전환", "강제로 전환", "force switchover"]}],
    },

    # ------------------------------------------------------------ NetScreen–FortiGate 상태 disable
    "q08": {
        "vendors": ["screenos", "fortigate"],
        "clues": ["터널 구간 통신 정상", "실제 데이터 전달 확인", "VPN 상태 표시만 disable"],
        "reference": [
            {"status": "confirmed_by_operator", "text": "모니터링 화면의 VPN 상태 표시는 Active / Inactive / Disable"},
            {"status": "unverified_case", "text": "현장 사례에서 1:1 터널링으로 해결했으나 일반 정답 여부는 미확정"},
            {"status": "scoring_rule", "text": "정답 일치가 아니라 단서와의 정합성으로 판정"},
        ],
        "excluded": [
            {
                "id": "협상 설정을 근거 없이 재구성",
                "keywords": [
                    "Phase 1 설정을 다시 구성", "Phase 2 설정을 다시 구성", "VPN을 재구성",
                    "proposal을 변경", "암호화 알고리즘을 변경", "암호화 알고리즘 변경",
                ],
            },
            {
                "id": "협상값 불일치를 주 원인으로 되돌림",
                "keywords": [
                    "Pre-shared Key가 불일치", "프리-쉐어드 키가 불일치",
                    "proposal 불일치가 원인", "협상값 불일치가 원인",
                ],
            },
        ],
        "contradicted": [
            {
                "id": "터널 미생성·협상 실패",
                "keywords": [
                    "터널이 생성되지", "터널은 생성되지", "터널 생성 실패",
                    "협상 실패", "협상이 실패", "VPN이 연결되지 않",
                ],
            },
            {
                "id": "SA 미생성",
                "keywords": ["SA 생성 실패", "SAD가 생성되지", "터널 자체가 구축되지"],
            },
        ],
        "facts_wrong": [],
        "facts_check": [
            {"id": "FortiGate IKEv2 전용 주장", "keywords": ["IKEv2 기반", "IKEv2만", "IKEv2를 사용하므로"]},
        ],
        "risky": [
            REBOOT,
            RESET,
            {"id": "터널 삭제·재생성", "keywords": ["터널을 삭제", "삭제 후 재생성", "터널을 재생성"]},
        ],
    },

    # ------------------------------------------------------------ Cisco SFP 미인식 / A/S
    "q09": {
        "vendors": ["cisco"],
        "clues": ["광 SFP 미인식", "Cisco 정품 확인됨", "정품 A/S 방식", "서드파티 A/S 방식"],
        "reference": [
            {
                "status": "confirmed_by_operator",
                "text": "정품은 유지보수 계약 또는 구매처·총판을 통해 TAC 케이스와 RMA 절차 확인",
            },
            {
                "status": "confirmed_by_operator",
                "text": "서드파티는 판매처 A/S가 기본이며 Cisco TAC가 정품 교체 후 재현을 요구하거나 지원을 제한할 수 있음",
            },
        ],
        "excluded": [
            {
                "id": "정품 여부를 처음부터 다시 판별",
                "keywords": ["정품 여부부터 다시", "정품인지 다시 확인", "위조 여부부터", "가품인지 확인부터"],
            },
        ],
        "contradicted": [
            {
                "id": "비정품이라고 단정",
                "keywords": ["서드파티 모듈이기 때문", "비정품이기 때문", "정품이 아니므로 인식되지"],
            },
        ],
        "facts_wrong": [
            {"id": "SFP 드라이버 설치", "keywords": ["드라이버를 다운", "드라이버를 업그레이드", "드라이버를 다운로드"]},
            {"id": "Advanced IP Services를 A/S 프로그램으로 설명", "keywords": ["A/S (Advanced IP Services)"]},
        ],
        "facts_check": [
            {"id": "A/S 프로그램 명칭", "keywords": ["Replacement Program", "교체 프로그램"]},
            {"id": "보증 기간 주장", "keywords": ["평생 보증", "lifetime", "Lifetime", "보증 기간"]},
        ],
        "risky": [
            {"id": "미지원 모듈 강제 인식", "keywords": ["service unsupported-transceiver", "no errdisable detect cause gbic-invalid"]},
            REBOOT,
            RESET,
        ],
    },

    # ------------------------------------------------------------ Cisco→Juniper 이전
    "q10": {
        "vendors": ["cisco", "junos"],
        "clues": [
            "양쪽 802.1Q 트렁크·VLAN ID 동일", "링크 up·LLDP 인식", "일부 VLAN만 불통",
            "포트 up 이후 간헐적 루프", "각 스위치 내부 통신 정상",
        ],
        "reference": [
            {
                "status": "verification_candidate",
                "text": "native VLAN 불일치, 허용 VLAN 목록 차이, PVST+/Rapid-PVST+와 RSTP 상호운용 문제 가설",
            },
            {
                "status": "verification_candidate",
                "text": "Junos native-vlan-id 위치는 ELS/non-ELS 계열과 모델·버전에 따라 확인 필요",
            },
        ],
        "excluded": [
            {
                "id": "VLAN ID 동일 여부만 다시 확인",
                "keywords": ["VLAN ID만 다시", "VLAN ID를 재확인", "VLAN ID 동일 여부부터"],
            },
            {
                "id": "물리 링크를 주 원인으로 되돌림",
                "keywords": ["케이블부터 교체", "물리 링크 장애가 원인", "링크 상태부터 다시 확인"],
            },
        ],
        "contradicted": [
            {
                "id": "링크·LLDP 인식 실패로 단정",
                "keywords": ["링크 다운이 원인", "링크가 down이므로", "LLDP가 인식되지 않아", "물리적으로 인식되지 않"],
            },
        ],
        "facts_wrong": [
            {
                "id": "STP 비활성화·포워딩 강제로 루프 해결",
                "keywords": [
                    "STP를 비활성화하여 루프를 해결", "STP 비활성화로 루프 해결",
                    "포트를 강제로 forwarding", "포워딩 모드로 강제하여 루프 해결",
                    "blocking 포트가 없어야 정상", "차단 상태 포트가 없어야 정상",
                ],
            },
        ],
        "facts_check": [
            {"id": "Junos native VLAN 설정", "keywords": ["native-vlan", "native vlan"]},
            {"id": "STP 기본 모드 주장", "keywords": ["기본적으로 RSTP", "기본 STP", "기본값은 RSTP", "기본값은 MSTP"]},
        ],
        "risky": [
            REBOOT,
            RESET,
            {
                "id": "STP 비활성화",
                "keywords": [
                    "no spanning-tree", "STP를 비활성화", "STP 비활성화",
                    "spanning-tree 비활성화", "delete protocols",
                ],
            },
            {"id": "포트 강제 포워딩", "keywords": ["강제로 forwarding", "포워딩 모드로 강제", "강제 포워딩"]},
        ],
    },
}


def validate_config():
    """설정 파일 자체의 기본 오류를 빠르게 확인한다."""
    assert set(RUBRIC) == {"A", "B", "C", "D", "E"}
    assert abs(sum(AXIS_WEIGHTS.values()) - 1.0) < 1e-9
    assert set(AXIS_WEIGHTS) == set(RUBRIC)
    assert set(ANSWER_KEYS) == {f"q{i:02d}" for i in range(1, 11)}

    for qid, key in ANSWER_KEYS.items():
        unknown_vendors = set(key["vendors"]) - VENDOR_NAMES
        assert not unknown_vendors, f"{qid}: unknown vendors: {unknown_vendors}"
        for required in ("clues", "excluded", "contradicted", "facts_wrong", "facts_check", "risky"):
            assert required in key, f"{qid}: missing {required}"
        for category in ("excluded", "contradicted", "facts_wrong", "facts_check", "risky"):
            for item in key[category]:
                assert item.get("id"), f"{qid}/{category}: missing id"
                assert item.get("keywords"), f"{qid}/{category}/{item.get('id')}: missing keywords"


if __name__ == "__main__":
    validate_config()
    print(f"rubric {RUBRIC_VERSION}: OK")