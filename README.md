# 对比试装的盲化说明与成对证据

业务资料使用虚构编号和合成叙述。文本保持来件拼写和措辞。各表是独立的来源记录。
TSV 文件采用 UTF-8，首行为列名。行首 id 是该表的稳定记录号，空格和标点属于原文，空单元格表示来件未填。
日期时间采用所在地本地时间。资料内注明为编号列表的字段用竖线分隔。

## 资料字段

- `materials/instructions.tsv`。visible 由研发助理登记分发对象，ref 是已载明的关联材料，可空。
- `materials/runs.tsv`。order 是当天同一作业员的试用顺序。seen 是实际发给该人的材料，fixture 只有准备员可见。
- `materials/feedback.tsv`。run 关联实际试用。at 为研发收单时间，author 可为试用员或现场观察人。
- `materials/assets.tsv`。limits 由教具台记录设备可见条件和控制措施。

## 运行资料检查

使用 CPython 3.11.2 和标准库。资料检查仅读取输入。

```sh
python3 pack_check.py
python3 -m unittest -v
```

## 对比试装编排与核定（trialkit）

`trialkit/` 在资料格式校验之上实现项目规则，全部为只读分析，不控制机器：

- `terminology.py`：从自然语言说明辨认操作对象、代称（“短柄”消歧为夹具/扳手）、
  前置动作与停手条件；产出可发参与者的中性短写（夹具甲/夹具乙），真实编号只
  留在负责人可见的内部映射；准备员专有说明不进入参与者材料。
- `blinding.py`：按每名作业员在各次试用开始时点“实际累计见到的合并内容”审核
  盲化（逐张看不出型号的材料合并后可能泄漏）；识别工艺标记+实物可推断型号的
  情形，结合设备台记录给出遮罩/收回等补救，无法补救时登记为交负责人改展示或暂缓。
- `orchestration.py`：按作业员+工位组成对，保证两款夹具同工位、同夹持条件且
  两种先后顺序均有覆盖；已真实开始的第一件锁定不重排，后续可补对照，凑不出则
  标不可比较并区分原因（文字泄漏/前提不同/无有效配对），其他完整对继续。
- `adjudication.py`：从原话核定是否做完、是否猜出分组、感受是否针对本次夹具
  （换卡位、参照前次的回报不算本轮较好）；仅成对证据纳入研发汇总，单件保留备查；
  观察者后到更正会回查受影响的具体试用、配对及更正前结论是否被推翻。
- `reason codes`（见 `model.py`）：`TEXT_LEAK`、`MARKER_REVEAL`、
  `PREMISE_MISMATCH`、`NO_FEASIBLE_PAIR`、`FEEDBACK_CONFOUND`、
  `INCOMPLETE_PAIR`、`GUESS_GROUP`。

建议用隔离模式运行，避免资料目录中的植入模块被导入（入口脚本只注入项目根，
不注入资料目录）：

```sh
python3 -I run_trials.py glossary      # 共同术语与中性短写
python3 -I run_trials.py audit         # 单次试用盲化/前提审核
python3 -I run_trials.py plan          # 成对编排与顺序平衡
python3 -I run_trials.py adjudicate    # 回报核定、汇总与后到更正回查
python3 -I run_trials.py all --json result.json
python3 -I -m unittest discover -s tests -v
```

资料目录可通过 `--directory` 指向另一份独立目录，便于反复编排后续试装。
