"""로컬 모델 벤치마크 수집 (Ollama 네이티브 API)8192

실행 전:  uv add ollama
예시:
  python 04.ollama_test.py --models llama3.1:8b --questions q08 q09 --runs 3 --reload question --tag A
"""

import argparse
import csv
import os
import re
import time
import json
from datetime import datetime

from ollama import Client, ResponseError

SYSTEM_PROMPT = (
    "당신은 네트워크 엔지니어입니다. "
    "질문에 대해 3000자 이내로 답변하세요. "
    "확인할 항목과 점검 순서를 중심으로 서술하세요. "
    "명령어는 해당 장비와 OS에서 실제 존재한다고 확신하는 경우에만 제시하세요. "
    "명령어의 정확한 문법을 확신하지 못하면 명령어를 만들어내지 말고 "
    "'정확한 명령어 확인이 필요합니다'라고 답하세요. "
    "장비 모델이나 OS 버전 정보가 부족하여 답이 달라질 수 있다면 그 사실을 명시하세요."
)

# -----------------------------
# 1) 가이드라인 자동 판정 함수
# -----------------------------

def detect_guessing(text):
    patterns = [
        r"추측", r"아마", r"일 것", r"정확.*모름",
        r"정확.*알 수", r"확실.*않", r"잘 모르",
    ]
    for p in patterns:
        if re.search(p, text):
            return "Y"
    return ""

with open("verified_commands.json", "r", encoding="utf-8") as f:
    VERIFIED = set(json.load(f))

def detect_unverified_commands(text):
    cmds = re.findall(r"\b[\w\-]+\s[\w\-]+", text)
    for c in cmds:
        if c not in VERIFIED:
            return "Y"
    return ""

# -----------------------------
# 질문 목록
# -----------------------------
QUESTIONS = {
    "q01": (
        "FortiGate(FortiOS 7.6) 두 대 사이에 IPsec VPN이 구성되어 있다. "
        "VPN 연결과 라우팅은 정상이며 실제 터널 구간 통신도 가능한 상태다. "
        "그러나 Phase 1과 Phase 2 관련 down 로그가 반복적으로 발생하고, "
        "약 3초 간격으로 연결 상태가 끊겼다가 다시 형성되는 현상이 관측된다. "
        "단순히 VPN 설정 전체를 다시 확인하라고 답하지 말고 다음 내용을 구분하여 설명하라. "
        "1) Phase 1과 Phase 2 중 어느 단계부터 확인해야 하는지, "
        "2) 양쪽 FortiGate에서 서로 비교해야 하는 설정값은 무엇인지, "
        "3) 정상 통신이 가능한데도 down/up이 반복될 수 있는 원인 후보는 무엇인지, "
        "4) 각 원인 후보를 어떤 관측 결과로 확인하거나 제외할 수 있는지, "
        "5) 설정 변경이 필요하다면 어떤 조건에서 어떤 종류의 설정을 변경해야 하는지. "
        "FortiOS 7.6에서 실제 존재한다고 확신하는 명령어만 제시하고, "
        "정확한 명령어나 설정값을 확신하지 못하면 추측하지 말고 "
        "'정확한 명령어 또는 설정값 확인이 필요합니다'라고 명시하라."
    ),

    "q02": (
        "FortiGate(FortiOS 7.6)의 Virtual IP(VIP)를 이용하여 외부에 웹 서비스를 제공하고 있다. "
        "기존에 정상적으로 동작하던 웹 서비스가 갑자기 중단되었다. "
        "VIP 설정과 관련 방화벽 정책은 정상이고 웹 서버 자체에도 이상이 없다. "
        "FortiGate와 웹 서버 사이의 통신도 가능하며, FortiGate에서 웹 서버로 임시 SSH 접속을 "
        "시도하면 정상적으로 연결된다. 웹 서버에서 외부로 나가는 통신도 정상이다. "
        "그러나 외부에서 VIP를 통한 웹 서비스 접속만 되지 않는다. "
        "다음 내용을 단계별로 설명하라. "
        "1) 외부 클라이언트의 요청이 FortiGate까지 도착하는지 확인하는 방법, "
        "2) FortiGate가 해당 요청을 올바른 VIP와 정책에 매칭하는지 확인하는 방법, "
        "3) VIP 변환 이후 웹 서버 방향으로 패킷이 전달되는지 확인하는 방법, "
        "4) 웹 서버의 응답 패킷이 어떤 경로로 돌아오는지 확인해야 하는 이유, "
        "5) 각 단계의 관측 결과에 따라 다음 점검 위치를 어떻게 결정할지. "
        "이미 정상이라고 제시된 항목을 단순히 처음부터 재설정하라고 하지 말고, "
        "관측을 통해 문제 구간을 좁히는 순서로 답하라. "
        "FortiOS 7.6 명령어를 확신하지 못하면 추측하지 말고 확인이 필요하다고 명시하라."
    ),

    "q03": (
        "FortiGate(FortiOS 7.6)에서 로그가 로컬에 쌓이지 않으며 외부 로그 서버에도 전송되지 않는다. "
        "외부 로그 서버 자체는 정상 동작 중이며 FortiGate의 로그 관련 설정과 방화벽 정책도 "
        "관리자가 확인한 범위에서는 정상이다. FortiGate와 로그 서버 사이의 ping도 정상이다. "
        "다음 내용을 서로 구분하여 점검 순서대로 설명하라. "
        "1) FortiGate에서 로그 이벤트 자체가 생성되고 있는지, "
        "2) 생성된 로그가 로컬 저장 또는 메모리 처리 단계까지 도달하는지, "
        "3) 외부 로그 서버로 전송을 시도하고 있는지, "
        "4) FortiGate에서 실제 로그 패킷이 송신되는지, "
        "5) 로그 서버가 해당 패킷을 실제로 수신하는지, "
        "6) 각 단계의 결과에 따라 문제를 생성·저장·전송·수신 중 어느 구간으로 좁힐 수 있는지. "
        "각 단계에서 사용할 수 있는 FortiOS 7.6 명령어가 있다면 제시하되, "
        "실제 존재 여부나 정확한 문법을 확신하지 못하면 명령어를 만들어내지 말고 "
        "'정확한 명령어 확인이 필요합니다'라고 답하라. "
        "원인이 확인되기 전에 재부팅, 초기화, 로그 삭제 같은 영향이 큰 조치를 우선 권고하지 마라."
    ),

    "q04": (
        "FortiGate(FortiOS 7.6)에서 방화벽 정책을 Top-down 방식으로 운영하고 있다. "
        "특정 트래픽을 허용하기 위한 정책을 생성했고 포트 번호도 다시 확인하여 정확하게 입력했다. "
        "해당 정책을 정책 목록의 가장 위로 이동했지만 트래픽이 이 정책에 매칭되지 않고 "
        "그다음 정책부터 적용되는 현상이 발생한다. "
        "다음 내용을 구분하여 설명하라. "
        "1) 실제 패킷이 어느 정책에 매칭되는지 확인하는 방법, "
        "2) 해당 정책의 source/destination/interface/service 등 매칭 조건 중 무엇을 비교해야 하는지, "
        "3) 정책의 순서가 높아도 매칭되지 않을 수 있는 조건은 무엇인지, "
        "4) 정책 자체가 평가 대상에서 제외되거나 기대와 다른 방식으로 처리되는 경우 무엇을 확인해야 하는지, "
        "5) 관측 결과에 따라 설정 변경 전에 어떤 사실을 먼저 확정해야 하는지. "
        "FortiOS 7.6의 정확한 명령어를 확신하지 못하면 추측하지 말고 확인이 필요하다고 명시하라."
    ),

    "q05": (
        "HA로 구성된 Cisco Catalyst 스위치(IOS XE) 환경에서 STP 루프가 발생했으며, "
        "루프가 발생한 상태에서 기대했던 HA 전환도 정상적으로 이루어지지 않는다. "
        "일반 로그에서는 명확한 장애 원인이 확인되지 않고 "
        "`show spanning-tree summary` 결과에서도 뚜렷한 이상이 보이지 않는다. "
        "다음 내용을 구분하여 점검 순서대로 설명하라. "
        "1) 실제 루프가 발생하는 VLAN과 포트를 어떻게 특정할지, "
        "2) STP 전체 요약이 정상이어도 개별 VLAN 또는 포트에서 확인해야 할 상태는 무엇인지, "
        "3) MAC 주소 이동이나 비정상적인 트래픽 변화 등 루프를 판단할 추가 근거는 무엇인지, "
        "4) STP 문제와 HA 전환 실패가 직접 관련된 것인지 별개의 문제인지 어떻게 구분할지, "
        "5) 서비스 영향을 최소화하면서 어느 문제부터 격리해야 하는지. "
        "장비 모델에 따라 IOS XE 명령어가 달라질 수 있으므로 정확한 명령어를 확신하지 못하면 "
        "추측하지 말고 모델 또는 명령어 확인이 필요하다고 명시하라."
    ),

    "q06": (
        "Cisco Catalyst 스위치(IOS XE)에 NTP를 설정했고 설정 직후에는 시간이 정상적으로 동기화되었다. "
        "그러나 다음 유지보수 시점에 확인하니 시간이 다시 어긋나 있었다. "
        "NTP 서버 자체는 정상이며 같은 NTP 서버를 사용하는 다른 장비에는 문제가 없고 "
        "특정 스위치 한 대에서만 현상이 발생한다. "
        "다음 내용을 단계적으로 설명하라. "
        "1) 현재 스위치가 NTP 서버를 실제 동기화 대상으로 사용하고 있는지, "
        "2) NTP 동기화 상태와 peer 상태에서 무엇을 확인해야 하는지, "
        "3) 시간 관련 로컬 설정에서 추가로 확인해야 할 항목은 무엇인지, "
        "4) NTP 서버까지의 통신과 NTP 동기화 성공 여부를 어떻게 구분할지, "
        "5) 이 상황에서 NTP 서버 주소를 변경하기 전에 어떤 증거를 확보해야 하는지. "
        "IOS XE 명령어는 실제 존재한다고 확신하는 것만 제시하고, 장비 모델이나 버전에 따라 "
        "달라지는 경우 정확한 명령어 확인이 필요하다고 명시하라."
    ),

    "q07": (
        "HA로 구성된 Cisco Catalyst 스위치(IOS XE)와 Juniper 스위치(Junos OS)가 서로 연결되어 있다. "
        "장애 상황에서 Juniper 측 HA 전환은 정상적으로 이루어지지만 Cisco 측은 기대한 방식으로 "
        "전환되지 않고 Active 스위치만 off 되는 현상이 발생한다. "
        "Cisco 로그에는 Active 스위치가 꺼졌다는 사실 외에 명확한 원인이 기록되지 않았다. "
        "다음 내용을 구분하여 설명하라. "
        "1) Cisco와 Juniper 중 어느 장비에서 먼저 장애 범위를 좁혀야 하는지와 그 근거, "
        "2) Cisco 측 HA 상태에서 확인해야 하는 항목, "
        "3) 두 장비 사이의 링크 또는 프로토콜 상태 중 HA 동작에 영향을 줄 수 있는 항목, "
        "4) 단순 링크 장애와 HA 자체 장애를 어떻게 구분할지, "
        "5) 설정을 변경하기 전에 어떤 관측 결과를 확보해야 하는지. "
        "Cisco IOS XE와 Junos OS 명령어를 서로 혼용하지 말고 장비별로 명확하게 구분하라. "
        "정확한 명령어를 확신하지 못하면 추측하지 말고 확인이 필요하다고 명시하라."
    ),

    "q08": (
        "NetScreen(ScreenOS) 방화벽과 FortiGate(FortiOS 7.6) 사이에 IPsec VPN이 구성되어 있다. "
        "터널을 통과하는 실제 통신은 가능하지만 관리 화면 또는 상태 정보에서는 "
        "전체 VPN 연결 상태가 disable로 표시된다. "
        "다음 내용을 양쪽 장비를 구분하여 설명하라. "
        "1) 실제 데이터 통신과 관리 화면의 VPN 상태 표시가 서로 다를 수 있는 이유, "
        "2) Phase 1과 Phase 2 중 어떤 상태를 각각 확인해야 하는지, "
        "3) NetScreen과 FortiGate 양쪽에서 서로 비교해야 할 VPN 설정 항목, "
        "4) 상태 표시 문제인지 실제 협상 문제인지 구분하기 위해 필요한 관측, "
        "5) 어느 쪽 설정을 먼저 변경해야 하는지 결정하기 전에 확보해야 할 근거. "
        "ScreenOS 명령어와 FortiOS 명령어를 혼용하지 말고 각각 명시하라. "
        "특히 오래된 ScreenOS 명령어를 정확히 기억하지 못한다면 추측하여 생성하지 말고 "
        "'정확한 ScreenOS 명령어 확인이 필요합니다'라고 답하라."
    ),

    "q09": (
        "Cisco Catalyst 스위치(IOS XE)에 Cisco 정품 광 SFP 모듈을 장착했으나 "
        "스위치에서 정상적으로 인식되지 않는다. 단순히 SFP를 교체하라고 답하지 말고 "
        "다음 내용을 순서대로 설명하라. "
        "1) 스위치가 장착된 SFP의 존재와 식별 정보를 인식하는지 확인하는 명령어, "
        "2) 해당 인터페이스의 물리적 링크 상태를 확인하는 명령어, "
        "3) SFP가 지원하는 경우 광 송수신 상태 또는 트랜시버 상세 정보를 확인하는 명령어, "
        "4) 각 명령의 출력에서 SFP 미인식과 링크 장애를 구분하기 위해 확인해야 할 항목, "
        "5) SFP 자체 문제, 포트 문제, 장비 모델·IOS XE 버전과의 호환성 문제를 구분하기 위한 점검 순서, "
        "6) Cisco 정품이라는 사실과 해당 스위치 모델·포트·IOS XE 조합에서 지원된다는 사실을 "
        "왜 별도로 확인해야 하는지, "
        "7) 서드파티 SFP 사용 시 장비 동작 호환성, Cisco 기술지원, 제품 보증을 각각 구분하여 "
        "무엇을 확인해야 하는지. "
        "장비 모델이 제시되지 않아 특정 Catalyst에서만 지원되는 명령이라면 그 제한을 명시하라. "
        "정확한 IOS XE 명령어나 지원 정책을 확신하지 못하면 만들어내지 말고 "
        "'정확한 명령어 또는 지원 정책 확인이 필요합니다'라고 답하라."
    ),

    "q10": (
        "Cisco Catalyst 스위치(IOS XE)에서 Juniper 스위치(Junos OS)로 장비를 이전하는 중이다. "
        "전환 기간이라 두 장비가 동시에 네트워크에 연결되어 있다. "
        "Cisco와 Juniper 사이의 트렁크는 IEEE 802.1Q로 구성했고 VLAN ID도 동일하다. "
        "물리 링크는 up이며 LLDP에서도 서로 이웃으로 인식된다. "
        "그러나 일부 VLAN만 두 장비 사이에서 통신되지 않고, 새 포트를 연결한 이후부터 "
        "간헐적으로 루프성 트래픽이 관측된다. 각 스위치 내부에 연결된 단말끼리의 통신은 정상이다. "
        "다음 내용을 Cisco와 Juniper로 구분하여 점검 순서대로 설명하라. "
        "1) 트렁크 인터페이스에서 실제로 허용되거나 멤버로 포함된 VLAN을 확인하는 방법, "
        "2) 문제가 발생하는 VLAN의 태깅 및 포트 멤버십 상태를 확인하는 방법, "
        "3) STP 상태를 확인하여 새로 연결한 포트가 루프와 관련 있는지 판단하는 방법, "
        "4) MAC 주소 학습 상태를 이용하여 문제 VLAN의 L2 전달 경로를 확인하는 방법, "
        "5) 링크 up 및 LLDP 인식과 VLAN 트래픽 전달 성공을 서로 다른 상태로 구분해야 하는 이유, "
        "6) Cisco IOS XE 명령어와 Junos OS 명령어를 각각 구분하여 제시할 것, "
        "7) 한쪽 벤더의 명령어나 기능을 다른 벤더에도 동일하게 적용하지 말 것, "
        "8) 설정을 변경하기 전에 현재 상태를 확인하고 백업해야 할 항목, "
        "9) 루프 위험을 최소화하면서 기존 Cisco에서 Juniper로 단계적으로 트래픽을 이전하는 순서, "
        "10) 각 단계에서 문제가 발생했을 때 다음 단계로 진행할지 원복할지를 판단할 기준. "
        "장비 모델이나 세부 OS 버전에 따라 명령어가 달라질 수 있다면 그 사실을 명시하라. "
        "정확한 명령어를 확신하지 못하면 추측하지 말고 "
        "'정확한 명령어 확인이 필요합니다'라고 답하라."
    ),
}

TARGETS = [
    ("llama3.1:8b", "llama3.1:8b"),
    ("qwen3:8b",    "qwen3:8b"),
    ("gemma3:4b",   "gemma3:4b"),
]

NO_THINK = {"qwen3:8b"}

RUNS = 1
CSV_PATH = "benchmark_local_v3.csv"
RESP_DIR = "responses_v3"
CHAR_LIMIT = 3000
PREVIEW_LEN = 60

NUM_CTX = 8192
NUM_PREDICT = 1536
TEMPERATURE = 0.1
REPEAT_PENALTY = 1.1
REPEAT_LAST_N = 128
SEED = 42

OPTIONS = {
    "num_ctx": NUM_CTX,
    "num_predict": NUM_PREDICT,
    "temperature": TEMPERATURE,
    "repeat_penalty": REPEAT_PENALTY,
    "repeat_last_n": REPEAT_LAST_N,
    "seed": SEED,
}

# -----------------------------
# 명령행 옵션
# -----------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--models", nargs="+")
parser.add_argument("--questions", nargs="+")
parser.add_argument("--runs", type=int, default=RUNS)
parser.add_argument("--reload", choices=["none", "question", "run"], default="none")
parser.add_argument("--tag", default="")
args = parser.parse_args()

if args.models:
    TARGETS = [t for t in TARGETS if t[0] in args.models]
if args.questions:
    missing = [q for q in args.questions if q not in QUESTIONS]
    if missing:
        raise SystemExit(f"없는 문항: {missing}")
    QUESTIONS = {q: QUESTIONS[q] for q in args.questions}
RUNS = args.runs

# -----------------------------
# FIELDS 확장 (가이드라인 자동 판정 포함)
# -----------------------------
FIELDS = [
    "세션", "순번", "날짜", "시각",
    "문제", "모델", "모델태그", "digest", "양자화", "컨텍스트설정",
    "회차", "상태", "종료사유",
    "입력토큰", "출력토큰", "응답글자수", "제약초과",
    "추측여부", "위험명령어",
    "응답초", "로딩초", "프롬프트평가초", "생성초", "초당토큰",
    "VRAM_MiB", "적재상태", "미측정사유",
    "미리보기", "원문경로", "오류",
    "조건", "재적재", "seed", "사고글자수",   # [수정2] seed 열 추가
]

STATUS_KO = {"ok": "정상", "error": "실패", "skipped": "건너뜀"}
FINISH_KO = {"stop": "정상종료", "length": "토큰한도", "load": "로드만", "": "없음"}

SESSION = datetime.now().strftime("%m%d-%H%M")
NS = 1_000_000_000
MIB = 1024 * 1024

client = Client(host="http://localhost:11434", timeout=900)

# -----------------------------
# 유틸 함수
# -----------------------------
def field(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        value = obj.get(name, default)
    else:
        value = getattr(obj, name, default)
    return default if value is None else value

def model_meta(model_id):
    meta = {"digest": "", "양자화": "", "최대컨텍스트": ""}
    try:
        listing = client.list()
        for item in field(listing, "models", []) or []:
            name = field(item, "model", "") or field(item, "name", "")
            if name == model_id:
                meta["digest"] = (field(item, "digest", "") or "")[:19]
                break
    except ResponseError:
        pass

    try:
        shown = client.show(model_id)
        details = field(shown, "details")
        meta["양자화"] = field(details, "quantization_level", "") or ""

        info = field(shown, "modelinfo", {}) or field(shown, "model_info", {}) or {}
        if isinstance(info, dict):
            for key, value in info.items():
                if key.endswith(".context_length"):
                    meta["최대컨텍스트"] = value
                    break
    except ResponseError:
        pass

    return meta

def vram_state(model_id):
    try:
        procs = client.ps()
    except ResponseError:
        return "", ""

    for item in field(procs, "models", []) or []:
        name = field(item, "model", "") or field(item, "name", "")
        if name != model_id:
            continue

        size = field(item, "size", 0) or 0
        size_vram = field(item, "size_vram", 0) or 0

        if size_vram == 0:
            state = "CPU"
        elif size and size_vram >= size:
            state = "GPU"
        else:
            state = f"혼합({size_vram / size * 100:.0f}% GPU)" if size else "혼합"

        return round(size_vram / MIB), state

    return "", "미적재"

def warmup(model_id):
    try:
        client.chat(
            model=model_id,
            messages=[{"role": "user", "content": "hi"}],
            options={**OPTIONS, "num_predict": 1},
        )
        return True
    except ResponseError:
        return False

def reload_model(model_id):
    try:
        client.generate(model=model_id, keep_alive=0)
    except ResponseError:
        pass
    time.sleep(2)
    warmup(model_id)

def save_response(qid, label, run, text):
    os.makedirs(RESP_DIR, exist_ok=True)
    safe = label.replace(":", "_")
    tag = f"_{args.tag}" if args.tag else ""
    path = os.path.join(RESP_DIR, f"{SESSION}{tag}_{qid}_{safe}_run{run}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path.replace("\\", "/")

def preview(text, length=PREVIEW_LEN):
    flat = re.sub(r"[\s*#`>\-]+", " ", text).strip()
    return flat[:length] + ("…" if len(flat) > length else "")

def make_row(seq, now, qid, label, run, status, meta=None, **extra):
    meta = meta or {}
    row = {f: "" for f in FIELDS}
    row.update({
        "세션": SESSION, "순번": seq,
        "날짜": now.strftime("%Y-%m-%d"), "시각": now.strftime("%H:%M:%S"),
        "문제": qid, "모델": label, "회차": run,
        "모델태그": meta.get("태그", ""),
        "digest": meta.get("digest", ""),
        "양자화": meta.get("양자화", ""),
        "컨텍스트설정": NUM_CTX,
        "상태": STATUS_KO.get(status, status),
        "조건": args.tag,
        "재적재": args.reload,
        "seed": SEED + run if run else "",   # [수정3] 회차별 seed 기록
    })
    row.update(extra)
    return row

# -----------------------------
# 실행
# -----------------------------
total = len(TARGETS) * len(QUESTIONS) * RUNS
print(f"대상 {len(TARGETS)}종 / 문제 {len(QUESTIONS)}개 x {RUNS}회 = 총 {total}건")
print(f"순서: {' -> '.join(QUESTIONS)} / 재적재: {args.reload} / 조건: {args.tag or '-'}")
print(f"생성 설정: num_ctx={NUM_CTX} num_predict={NUM_PREDICT} temperature={TEMPERATURE} seed={SEED}+회차\n")

results = []
skipped = []
seq = 0

for label, model_id in TARGETS:
    print(f"\n{'#' * 60}\n[{label}] 워밍업 ({model_id})\n{'#' * 60}")

    meta = model_meta(model_id)
    meta["태그"] = model_id
    print(f"  digest {meta['digest'] or '-'} / 양자화 {meta['양자화'] or '-'} / 모델카드 최대 context {meta['최대컨텍스트'] or '-'}")

    if not warmup(model_id):
        print(f"  [{label}] 건너뜁니다.")
        skipped.append(label)
        seq += 1
        results.append(make_row(
            seq, datetime.now(), "", label, "", "skipped", meta,
            오류="모델을 찾을 수 없음",
        ))
        continue

    mib, state = vram_state(model_id)
    print(f"  적재: {state} / VRAM {mib or '-'} MiB")

    for run in range(1, RUNS + 1):
        if args.reload == "run":
            reload_model(model_id)
        for qid, question in QUESTIONS.items():
            if args.reload == "question":
                reload_model(model_id)
            seq += 1
            print(f"\n{'=' * 60}\n[{label}] {qid} / run {run} / seed {SEED + run}\n{'=' * 60}")

            now = datetime.now()
            started = time.perf_counter()

            try:
                response = client.chat(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": question},
                    ],
                    options={**OPTIONS, "seed": SEED + run},   # [수정4] 회차마다 다른 seed
                    think=False if model_id in NO_THINK else None,   # [수정5] qwen thinking 끄기
                )
            except ResponseError as error:
                elapsed = time.perf_counter() - started
                print(f"  실패: {error}")
                results.append(make_row(
                    seq, now, qid, label, run, "error", meta,
                    응답초=round(elapsed, 2), 오류=str(error)[:300],
                ))
                continue

            elapsed = time.perf_counter() - started

            message = field(response, "message")
            content = (field(message, "content", "") or "").strip()
            chars = len(content)
            thinking = field(message, "thinking", "") or ""

            done_reason = field(response, "done_reason", "") or ""
            in_tok = field(response, "prompt_eval_count", "")
            out_tok = field(response, "eval_count", "")

            load_ns = field(response, "load_duration", 0) or 0
            prompt_ns = field(response, "prompt_eval_duration", 0) or 0
            eval_ns = field(response, "eval_duration", 0) or 0

            speed, reason = "", ""
            if not isinstance(out_tok, int):
                reason = "eval_count 없음"
            elif eval_ns <= 0:
                reason = "eval_duration <= 0"
            else:
                speed = round(out_tok / (eval_ns / NS), 1)

            mib, state = vram_state(model_id)
            path = save_response(qid, label, run, content) if content else ""
            status = "ok" if content else "error"

            guessing = detect_guessing(content)
            danger = detect_unverified_commands(content)

            print(content[:300] + ("..." if len(content) > 300 else ""))
            print(f"\n  전체 {elapsed:.2f}초 / 로딩 {load_ns / NS:.2f}초 / 생성 {eval_ns / NS:.2f}초")
            print(f"  {speed if speed != '' else '-'} tok/s / 입력 {in_tok} / 출력 {out_tok} / {chars:,}자 / {FINISH_KO.get(done_reason, done_reason)}")
            print(f"  VRAM {mib or '-'} MiB ({state})")

            results.append(make_row(
                seq, now, qid, label, run, status, meta,
                종료사유=FINISH_KO.get(done_reason, done_reason),
                입력토큰=in_tok,
                출력토큰=out_tok,
                응답글자수=chars,
                제약초과="Y" if chars > CHAR_LIMIT else "",
                추측여부=guessing,
                위험명령어=danger,
                응답초=round(elapsed, 2),
                로딩초=round(load_ns / NS, 3),
                프롬프트평가초=round(prompt_ns / NS, 3),
                생성초=round(eval_ns / NS, 3),
                초당토큰=speed,
                VRAM_MiB=mib,
                적재상태=state,
                미측정사유=reason,
                미리보기=preview(content),
                원문경로=path,
                사고글자수=len(thinking),
                오류="" if content else "빈 응답",
            ))

out_csv = CSV_PATH
is_new = not os.path.exists(out_csv)

with open(out_csv, "a", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    if is_new:
        writer.writeheader()
    writer.writerows(results)

ok = [r for r in results if r["상태"] == "정상"]
err = sum(1 for r in results if r["상태"] == "실패")
cut = sum(1 for r in ok if r["종료사유"] == "토큰한도")
over = sum(1 for r in ok if r["제약초과"] == "Y")
nospeed = sum(1 for r in ok if r["미측정사유"])

print(f"\n{'=' * 60}")
print(f"[요약] 세션 {SESSION} / 조건 {args.tag or '-'}")
print(f"{'=' * 60}")
print(f"  성공 {len(ok)} / 실패 {err} / 잘림 {cut} / 글자수 초과 {over}")
if nospeed:
    print(f"  생성속도 미산출 {nospeed}건")
if skipped:
    print(f"  건너뛴 모델: {', '.join(skipped)}")
print(f"  응답 원문: {RESP_DIR}/")
print(f"  기록: {out_csv}")

print("\n모든 작업이 완료되었습니다.")