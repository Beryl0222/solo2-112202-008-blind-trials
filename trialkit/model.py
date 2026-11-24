"""领域模型与原因代码。

原因代码贯穿编排与核定两个阶段，便于区分：
- TEXT_LEAK：文字说明（实际见到的合并内容）泄漏了分组身份；
- PREMISE_MISMATCH：两件的动作前提（前置说明、设备条件）不一致；
- NO_FEASIBLE_PAIR：没有真实开始件可锁定、也没有满足约束的对照可补齐；
- FEEDBACK_CONFOUND：回报感受混入非本次夹具因素，不能归到本轮夹具；
- INCOMPLETE_PAIR：仅完成单件，配对证据不完整。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------- 原因代码

class ReasonCode(str, Enum):
    """不可比较/不可采纳的原因分类。"""

    TEXT_LEAK = "TEXT_LEAK"                 # 说明文字泄漏分组
    MARKER_REVEAL = "MARKER_REVEAL"         # 工艺标记+实物可推断型号（文字泄漏的子类）
    PREMISE_MISMATCH = "PREMISE_MISMATCH"   # 动作前提不同
    NO_FEASIBLE_PAIR = "NO_FEASIBLE_PAIR"   # 凑不出有效配对
    FEEDBACK_CONFOUND = "FEEDBACK_CONFOUND"  # 感受不针对本次夹具
    INCOMPLETE_PAIR = "INCOMPLETE_PAIR"    # 单件，配对不完整
    GUESS_GROUP = "GUESS_GROUP"             # 参与者猜出分组


REASON_TEXT = {
    ReasonCode.TEXT_LEAK: "文字说明泄漏分组身份",
    ReasonCode.MARKER_REVEAL: "工艺标记与实物组合可推断型号",
    ReasonCode.PREMISE_MISMATCH: "两件动作前提不一致",
    ReasonCode.NO_FEASIBLE_PAIR: "无法在相同工位/夹持条件下补齐对照",
    ReasonCode.FEEDBACK_CONFOUND: "回报感受混入非本次夹具因素",
    ReasonCode.INCOMPLETE_PAIR: "仅完成单件，缺少成对证据",
    ReasonCode.GUESS_GROUP: "参与者在回报中表明已猜出分组",
}

# 盲法阶段（文字层面）产生的原因
BLINDING_REASONS = {ReasonCode.TEXT_LEAK, ReasonCode.MARKER_REVEAL}
# 编排阶段的结构性原因
STRUCTURAL_REASONS = {
    ReasonCode.PREMISE_MISMATCH,
    ReasonCode.NO_FEASIBLE_PAIR,
    ReasonCode.INCOMPLETE_PAIR,
}


# ---------------------------------------------------------------- 枚举

class Phase(str, Enum):
    DONE = "已做"
    TODO = "待做"
    PLANNED = "拟排"

    @property
    def started(self) -> bool:
        """已真实开始的试用不能重新排序。"""
        return self is Phase.DONE


class TermKind(str, Enum):
    """自然语言中一个术语的归属。"""

    FIXTURE = "fixture"        # 待比较的夹具 K2/K3
    SHARED_TOOL = "tool"       # 两组都用的扳手等共同工具
    MARKER = "marker"          # 工艺标记（凹点等准备员专有线索）
    COMMON = "common"          # 不区分分组的共同动作术语


# ---------------------------------------------------------------- 数据类

@dataclass(frozen=True)
class Instruction:
    id: str
    visible: str
    ref: tuple[str, ...]
    text: str

    @property
    def participant_visible(self) -> bool:
        return self.visible != "准备员"

    @property
    def prep_only(self) -> bool:
        return self.visible == "准备员"


@dataclass(frozen=True)
class Run:
    id: str
    worker: str
    order: int
    station: str
    fixture: str
    seen: tuple[str, ...]
    phase: Phase


@dataclass(frozen=True)
class Feedback:
    id: str
    run: str
    at: str
    author: str
    text: str

    @property
    def is_observer(self) -> bool:
        return self.author == "观察者"


@dataclass(frozen=True)
class Asset:
    id: str
    station: str
    limits: str


@dataclass
class TermUse:
    """一个术语在说明中的一次出现及其辨认结果。"""

    term: str
    kind: TermKind
    instruction_id: str
    detail: str = ""


@dataclass
class Glossary:
    """可发给参与者的共同术语与不泄漏分组的短写。"""

    common_terms: list[TermUse] = field(default_factory=list)
    # 短写 -> 说明（对参与者可见的中性写法）
    neutral_aliases: dict[str, str] = field(default_factory=dict)
    # 仅供试验负责人/准备员使用的真实指向
    internal_mapping: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class LeakFinding:
    """一次盲化审核发现。"""

    instruction_id: str
    code: ReasonCode
    explanation: str
    # 该发现需要与哪些其他材料/实物合并才成立
    combined_with: tuple[str, ...] = ()


@dataclass
class StationRemedy:
    """设备台记录的、可由准备人员执行的不泄漏展示方法。"""

    station: str
    asset_id: str
    cover_marker: bool = False          # 可用罩遮住表面标记
    recall_paper: bool = False          # 纸本可收回
    note: str = ""


@dataclass
class RunAudit:
    """对单次试用在开始时点的盲化/前提审核。"""

    run_id: str
    seen_materials: tuple[str, ...]
    findings: list[LeakFinding] = field(default_factory=list)
    prerequisites_available: bool = True
    missing_prerequisites: tuple[str, ...] = ()
    remedies: list[StationRemedy] = field(default_factory=list)
    escalate: bool = False              # 无可用补救时交负责人改展示或暂缓

    @property
    def clean(self) -> bool:
        return not self.findings and self.prerequisites_available and not self.escalate

    @property
    def reason_codes(self) -> set[ReasonCode]:
        return {f.code for f in self.findings}


@dataclass
class PairPlan:
    """一名作业员在一个工位上的成对安排。"""

    worker: str
    station: str
    first: Run | None = None
    second: Run | None = None
    # 编排阶段已确定的结构性/盲化原因
    reason_codes: set[ReasonCode] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    remedies: list[StationRemedy] = field(default_factory=list)

    @property
    def fixtures(self) -> tuple[str | None, str | None]:
        return (
            self.first.fixture if self.first else None,
            self.second.fixture if self.second else None,
        )

    @property
    def locked_first(self) -> bool:
        return bool(self.first and self.first.phase.started)

    @property
    def structurally_complete(self) -> bool:
        return self.first is not None and self.second is not None

    @property
    def counterbalanced(self) -> bool:
        """两件夹具各出现一次、顺序不同（相对另一对）的单对判定：两件互不相同。"""
        a, b = self.fixtures
        return a is not None and b is not None and a != b


@dataclass
class FeedbackVerdict:
    """单件回报的核定结果。"""

    feedback_id: str
    run_id: str
    completed: bool                     # 是否按有效前提做完
    guesses_group: bool                 # 是否猜出分组
    fixture_targeted: bool              # 感受是否针对本次夹具
    feel: str | None                    # 从原话得到的手感方向（轻/难推/中性）
    flags: list[str] = field(default_factory=list)
    explanations: list[str] = field(default_factory=list)
    corrections: tuple[str, ...] = ()   # 影响该核定的后到更正记录


@dataclass
class PairEvidence:
    """核定后的一对证据。"""

    worker: str
    station: str
    first_run: str | None
    second_run: str | None
    comparable: bool
    reason_codes: set[ReasonCode] = field(default_factory=set)
    verdicts: list[FeedbackVerdict] = field(default_factory=list)
    note: str = ""
    # 该对中被后到更正触发重审的具体试用
    reaudited_runs: tuple[str, ...] = ()
    # 若没有后到更正，这一对原本是否可比较（用于回查哪些结论被推翻）
    comparable_before_correction: bool | None = None
    corrections: tuple[str, ...] = ()

    @property
    def feel_comparison(self) -> str | None:
        """可比较时给出基于原话的手感对比描述，否则为 None。"""
        if not self.comparable:
            return None
        feels = [v.feel for v in self.verdicts if v.feel]
        return " / ".join(feels) if feels else None


@dataclass
class Correction:
    """后到更正（如观察者补登记实际所见材料）。"""

    feedback_id: str
    run_id: str
    extra_seen: tuple[str, ...]
    text: str
    at: str
