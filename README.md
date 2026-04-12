# CAMO

CAMO（Character Modeling & Simulation Base）是一个把非结构化文本中的人物，转成可复用、可交互、可持续运行的角色资产的基础项目。

CAMO (Character Modeling & Simulation Base) is a foundation for turning characters described in unstructured text into reusable, interactive, and durable character assets.

它面向小说、聊天记录、剧本、访谈、wiki 等文本来源，目标是沉淀出人物画像、关系、记忆、语言风格和运行约束，供上层角色类应用使用。

It is designed for source material such as novels, chat logs, scripts, interviews, and wikis, with the goal of producing character profiles, relationships, memory, speaking style, and runtime constraints for higher-level character products.

## 项目现状 | Current Status

当前仓库以文档为主，还没有正式实现代码。现阶段内容主要用于定义项目要解决什么问题、分阶段要做到什么、以及第一版技术路线准备怎么落地。

This repository is currently documentation-first and does not yet contain a production implementation. At this stage, it mainly defines the problem space, the phased roadmap, and the first planned implementation route.

## 核心文档 | Key Documents

- [产品方案 v0.2 / Product Requirements v0.2](docs/CAMO_PRD-v0.2.md): 当前版本的产品定义、范围、目标、架构、数据模型、评测方式和里程碑; the current product definition, scope, goals, architecture, data model, evaluation approach, and milestones
- [技术设计 v0.1 / Technical Design v0.1](docs/CAMO_TDD-v0.1.md): 基于 PRD v0.2 的第一版技术实现方案; the first technical implementation plan based on PRD v0.2
- [产品方案 v0.1 / Product Requirements v0.1](docs/CAMO_PRD-v0.1.md): 更早期的产品草案，保留用于对照演进过程; the earlier product draft kept for comparison

## 建议阅读顺序 | Suggested Reading Order

1. 先看 [产品方案 v0.2 / Product Requirements v0.2](docs/CAMO_PRD-v0.2.md)，了解项目是什么、做什么、不做什么。 Start here to understand what the project is, what it covers, and what it does not cover.
2. 再看 [技术设计 v0.1 / Technical Design v0.1](docs/CAMO_TDD-v0.1.md)，了解第一阶段到第二阶段准备如何实现。 Continue here to see how the first implementation path is intended to work.
3. 如果需要回看思路演进，再看 [产品方案 v0.1 / Product Requirements v0.1](docs/CAMO_PRD-v0.1.md)。 Use this only if you want to compare how the idea evolved.

## 当前覆盖范围 | What CAMO Covers

- 从文本中抽取角色 / character extraction from text
- 结构化人物建模 / structured character modeling
- 人物关系图谱 / relationship graph construction
- 事件与记忆组织 / event and memory organization
- 面向角色回复的运行时能力 / runtime support for in-character responses
- 角色一致性与知识边界控制 / consistency checks for role behavior and knowledge boundaries

## 当前不覆盖 | Out of Scope

- 面向终端用户的产品界面 / end-user product UI
- 模型训练或微调 / model training or fine-tuning
- 通用平台级内容审核 / general-purpose platform moderation
- 以非人物实体为主的通用知识库 / a general knowledge base centered on non-character entities
- 实时语音或视频生成 / real-time voice or video generation

## 规划方向 | Planned Direction

1. 先完成人物理解引擎 / First, build the character understanding engine.
2. 再完成单角色运行时 / Then, build the single-character runtime.
3. 之后扩展到多角色仿真 / After that, extend toward multi-character simulation.

## 仓库结构 | Repository Structure

```text
CAMO/
├── README.md
└── docs/
    ├── CAMO_PRD-v0.1.md
    ├── CAMO_PRD-v0.2.md
    └── CAMO_TDD-v0.1.md
```

## 备注 | Notes

- 当前最新的产品文档是 `docs/CAMO_PRD-v0.2.md` / The latest product document in this repository is `docs/CAMO_PRD-v0.2.md`.
- 当前最新的技术方案文档是 `docs/CAMO_TDD-v0.1.md` / The latest technical design document in this repository is `docs/CAMO_TDD-v0.1.md`.
