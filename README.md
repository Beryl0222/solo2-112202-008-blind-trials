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
