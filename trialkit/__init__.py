"""对比试装项目：盲化说明审核、成对编排与试用核定。

子模块：
- model：领域数据结构与原因代码
- loading：在资料包格式校验之上的对象装载
- terminology：从自然语言说明中辨认操作对象、代称、前置条件与准备员专有信息
- blinding：按参与者实际见到的合并内容做盲化泄漏审核
- orchestration：成对试用编排、锁定规则与不可比较原因
- adjudication：操作回报核定、配对证据汇总与后到更正的回查
- reporting / cli：输出与命令行入口
"""

__all__ = [
    "model",
    "loading",
    "terminology",
    "blinding",
    "orchestration",
    "adjudication",
    "reporting",
]
