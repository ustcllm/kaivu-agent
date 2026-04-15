# Kaivu：Prompt 驱动的科学智能体设计

这是一份设计确认稿，不表示当前代码已经全部按此实现。它的目的，是在重构代码之前，把 Kaivu 接下来应该采用的科学智能体架构讲清楚。

## 核心立场

Kaivu 不应该变成一个为每个学科硬编码大量 workflow 的系统。更合理的方向是：基础系统提供稳定的科研生命周期和运行治理能力，而学科相关的科学推理，主要交给大模型通过 prompt、profile、schema、validator 和 tool capability 来完成。

核心原则是：

> 让大模型负责科学思考，让 Kaivu 负责科学治理。

也就是说，系统应该负责：

- 上下文构建、压缩、召回和 memory 边界管理。
- 工具能力解析和运行时策略控制。
- 证据、产物、溯源和 trajectory 记录。
- 质量闸门、评审记录、benchmark 评估和 replay。
- 向本地、远程、Kaggle、仿真或实验室环境进行执行交接。
- 可复现性、可审计性和多智能体协作。

系统不应该过度负责：

- 可以用 prompt 表达的学科推理经验。
- 生命周期结构相同但表述不同的 per-discipline workflow。
- 主要只是 prompt 不同的大型子类继承树。

## 最小硬编码原则

不同学科之间当然存在差异，但 Kaivu 不应该把“大模型已经能做的科学判断”写死在代码里。代码层真正必须硬编码的，是那些需要确定性执行、审计、复现、安全控制或格式约束的部分。

应该硬编码：

- schema、数据结构和 artifact contract。
- tool call 协议和 executor handoff 协议。
- 权限、安全、审批、预算和 sandbox policy。
- memory scope、graph diff、provenance 和 trajectory 记录规则。
- deterministic validator，例如 JSON schema、文件存在性、metric 计算、submission 格式、单位换算、parser。
- 外部环境接口，例如 local Python、Kaggle、AI training、simulation、cluster、instrument adapter。

不应优先硬编码：

- 如何提出科学假说。
- 如何解释机制或理论意义。
- 如何判断一个研究 idea 是否有趣。
- 如何归因文献冲突。
- 如何解释非确定性的实验失败。
- 多智能体组会里的立场和科学争论。
- 大多数 `design_experiment`、`interpret_result`、`classify_failure`、`decide_next_action` 的学科风格差异。

这些内容应该优先交给 LLM，并由 `DisciplineProfile`、schema、quality gate、failure taxonomy、evidence record 和 runtime policy 约束。

## 目标架构

```text
Interface Layer
  -> Web Workbench / CLI / API / 定时科研任务

ResearchDirector
  -> 项目级科研总控
  -> 选择 mission、agent、runtime、profile、task adapter
  -> 协调 group work、campaign plan、组会、报告

ScientificAgentRuntime
  -> 运行生命周期 stage
  -> 构建上下文
  -> 解析 capability
  -> 调用工具和 executor
  -> 执行运行时 policy
  -> 记录 trajectory、memory diff、graph diff、tool call、feedback

ScientificAgent
  -> 稳定的科研生命周期骨架
  -> 定义 stage interface
  -> 把学科判断交给 profile、prompt、validator 和必要 hook

DisciplineProfile
  -> 学科 prompt
  -> schema hint
  -> quality gate
  -> evidence convention
  -> failure taxonomy
  -> decision criteria

TaskAdapter
  -> 任务输入规范化
  -> 任务输出契约
  -> 任务约束和外部环境元信息

ScientificCapabilityRegistry
  -> 把抽象科学能力映射到具体工具
  -> 记录 execution mode、approval requirement 和 capability pack

KnowledgeSubstrate
  -> personal memory
  -> group memory
  -> project memory
  -> literature digest/wiki
  -> failed attempts
  -> provenance graph
  -> artifact registry

ResearchExecutionEnvironment
  -> local Python
  -> Kaggle
  -> AI training
  -> simulation
  -> cluster
  -> lab/instrument adapter

Learning and Evaluation Layer
  -> episode schema
  -> trajectory replay
  -> benchmark harness
  -> human feedback
  -> future reward modeling and agentic RL
```

## 依赖方向

主要依赖方向应该以组合为主，而不是到处继承：

```text
ResearchDirector
  uses ScientificAgentRuntime
  uses ScientificAgent 或某个 discipline agent
  uses DisciplineProfile
  uses TaskAdapter

ScientificAgentRuntime
  uses ScientificCapabilityRegistry
  uses ContextManager
  uses MemoryManager
  uses GraphManager
  uses ToolExecutor
  uses ResearchExecutionEnvironment
  records Episode / Trajectory

ScientificAgent
  defines lifecycle hooks
  builds stage requests
  produces structured scientific outputs
  does not directly execute tools
  does not directly write memory or graph state
```

只有真正的学科智能体才应该从 `ScientificAgent` 继承。runtime、director、tools、memory、graph、model routing 和 execution environment 都应该通过组合接入系统，而不是通过继承接入。

## 科研生命周期骨架

不同学科应该共享一个稳定的科研生命周期：

```text
定义问题
  -> 收集上下文
  -> 文献调研
  -> 形成假说
  -> 编译预测
  -> 校验假说
  -> 设计测试或实验
  -> 规划执行
  -> 执行或交接执行
  -> 分析证据
  -> 分类失败
  -> 更新信念
  -> 决定下一步
  -> 更新 memory 和 graph
  -> 生成报告
```

不同学科通常不应该替换整条生命周期，而应该细化每个 stage 的 prompt、schema、validator、tool capability、executor 和解释规则。

## Stage 执行模式

每个生命周期 stage 都应该声明它是如何执行的。这样可以避免把子类覆写变成默认机制。

| Stage | 默认执行模式 | 说明 |
| --- | --- | --- |
| `frame_problem` | `llm_profile_driven + schema_driven` | 大模型根据学科 profile 和 task adapter 来定义问题。 |
| `gather_context` | `runtime_context_driven` | runtime 召回 memory、literature digest、graph、历史失败和项目约束。 |
| `review_literature` | `llm_profile_driven + capability_registry_driven` | 生命周期相同，但不同学科的来源偏好和质量标准不同。 |
| `formulate_hypotheses` | `llm_profile_driven + schema_driven` | 假说形式随学科变化，但大多数差异可以由 schema 表达。 |
| `compile_predictions` | `schema_driven + llm_profile_driven` | 预测需要明确、可证伪，并且能连接到证据。 |
| `validate_hypotheses` | `quality_gate_driven + llm_judge_driven` | validator 检查创新性、可行性、可证伪性、风险和学科约束。 |
| `design_experiment` | `llm_profile_driven + quality_gate_driven` | 通常 prompt/profile 足够，除非该学科需要确定性的 protocol 逻辑。 |
| `plan_execution` | `capability_registry_driven + runtime_policy_driven` | runtime 解析工具和执行环境。 |
| `execute_or_handoff` | `executor_handoff_driven` | agent 提出执行意图，runtime 在 policy 下执行或交接。 |
| `interpret_result` | `llm_profile_driven + evidence_schema_driven` | 只要 evidence schema 足够强，通常 prompt/profile 足够。 |
| `classify_failure` | `failure_taxonomy_driven + llm_profile_driven` | 失败分类优先放在 profile 数据里，其次才用代码覆写。 |
| `update_beliefs` | `evidence_policy_driven + llm_judge_driven` | 防止一次弱结果导致过度自信的信念更新。 |
| `decide_next_action` | `decision_policy_driven + llm_judge_driven` | planner/search 默认可以使用 LLM judge。 |
| `update_memory_and_graph` | `runtime_governed` | runtime 写入经过审计的 memory diff 和 graph diff，而不是 agent 直接写。 |
| `report` | `schema_driven + llm_profile_driven` | 报告应该从 evidence、graph、memory 和 trajectory 生成。 |

## Prompt 驱动优先，代码覆写其次

下面这些生命周期环节，默认应该由 prompt/profile 驱动：

- `design_experiment`
- `interpret_result`
- `classify_failure`
- `decide_next_action`
- `tool_capabilities_for_stage`
- `build_literature_plan`
- `synthesize_hypotheses`
- `validate_hypothesis`

如果差异可以通过下面这些机制表达，就不应该写子类覆写：

- 学科 profile prompt。
- 结构化输出 schema。
- quality gate 配置。
- failure taxonomy。
- capability requirement。
- runtime policy。
- task adapter。

子类覆写应该用于硬行为，而不是用于软性的科学风格差异。

## 什么时候不应该创建学科子类

当差异主要是下面这些内容时，不应该新建子类：

- prompt wording 不同。
- 文献质量标准不同。
- 输出 schema label 不同。
- preferred tool 不同。
- failure taxonomy 术语不同。
- next-action preference 不同。
- report format 不同。

这些差异应该优先放进 `DisciplineProfile`、`TaskAdapter`、`QualityGateRegistry`、`FailureTaxonomyRegistry` 和 `ScientificCapabilityRegistry`。

## 什么时候应该创建学科子类

只有当某个学科需要无法安全配置化的行为时，才应该创建或保留学科子类。

典型情况包括：

- 需要独特的 state machine。
- 需要确定性的 parser 或 validator。
- 执行环境有学科特定的 handoff protocol。
- 安全关键逻辑必须在大模型之外强制执行。
- 证据更新规则有不可妥协的语义。
- 工具链有学科特定 artifact 格式，需要代码级处理。
- agent 需要在多个 stage 之间维护学科特定内部状态。

这样可以让子类变少，但每个子类都真正有意义。

## 建议的核心对象

### `ResearchDirector`

`ResearchDirector` 是项目级科研控制层，更像科研项目负责人，而不是普通 workflow runner。

职责：

- 选择 research mission、agent、runtime、profile 和 task adapter。
- 协调 research campaign planning。
- 协调多智能体组会和 review loop。
- 在高层管理 project、group 和 user context。
- 生成项目级 report、manifest 和 state summary。

非职责：

- 不应该运行低层工具调用。
- 不应该实现学科特定的实验解释。
- 不应该直接写 memory 或 provenance graph 内部状态。

### `ScientificAgentRuntime`

`ScientificAgentRuntime` 在 policy 约束下运行单个科学智能体生命周期。

职责：

- 构建 stage context。
- 解析 stage capability。
- 调用工具和 executor。
- 执行 approval 和 safety policy。
- 记录 trajectory、tool call、memory diff、graph diff、artifact、score 和 feedback。
- 把工具结果回灌给生命周期 stage。

非职责：

- 不应该判断一个化学失败在科学上意味着什么。
- 不应该判断某个数学证明策略是否有前途。
- 不应该编码学科科学判断，除非这些判断属于 policy 或 schema enforcement。

### `ScientificAgent`

`ScientificAgent` 定义科研生命周期和结构化 stage interface。

职责：

- 声明生命周期 stage。
- 根据 profile、context、task 和 prior evidence 构建 stage prompt。
- 生成结构化科学输出。
- 为真正需要硬编码的学科行为暴露可选 hook。

非职责：

- 不应该直接执行工具。
- 不应该直接修改 memory。
- 不应该负责项目级 orchestration。
- 不应该硬编码每个学科的 workflow。

### `DisciplineProfile`

`DisciplineProfile` 应该是承载学科差异的首选位置。

它应该包含：

- 学科身份和基本假设。
- stage prompt template。
- hypothesis format convention。
- evidence convention。
- literature quality rule。
- quality gate。
- failure taxonomy。
- decision criteria。
- preferred capability。
- report convention。

例子：

- AI profile：benchmark validity、data leakage、ablation quality、seed sensitivity、compute budget。
- Chemistry profile：reaction condition、safety、yield、selectivity、characterization、side reaction taxonomy。
- Physics profile：observable definition、calibration、uncertainty propagation、simulation 和 measurement 的区分。
- Mathematics profile：conjecture、lemma、proof gap、counterexample、formal verification readiness。

### `TaskAdapter`

`TaskAdapter` 负责具体任务的输入输出语义，但不应该创建新的生命周期。

例子：

- `KaggleTaskAdapter` 规范化 competition description、dataset metadata、metric、leaderboard constraint、submission format 和 compute limit。
- `AIResearchTaskAdapter` 规范化 research question、benchmark、dataset、model family、training constraint 和 evaluation protocol。
- `ChemistrySynthesisTaskAdapter` 规范化 target molecule/material、reagent constraint、route constraint、safety constraint 和 available measurement。

对于 Kaggle，更合理的设计通常是：

```text
ArtificialIntelligence profile
  + KaggleTaskAdapter
  + Kaggle capability pack
  + Kaggle execution environment
```

这比把 Kaggle 做成一条完全独立的 workflow 更好。

### `ScientificCapabilityRegistry`

`ScientificCapabilityRegistry` 把抽象科学能力映射到具体工具。

例子：

- `literature_search` -> `arxiv_search`、`crossref_search`、`pubmed_search`
- `python_analysis` -> local Python executor
- `ai_training_execution` -> training executor
- `kaggle_submission_dry_run` -> Kaggle executor
- `proof_checking` -> proof assistant 或 symbolic checker
- `chemistry_safety_review` -> safety checker

agent 应该请求 capability，runtime 应该选择具体工具。

## 工具调用关系

agent 不应该直接调用工具。

推荐流程：

```text
ScientificAgent
  -> 生成 StageRequest
  -> 包含需要的 capability、expected schema 和 rationale

ScientificAgentRuntime
  -> 检查 policy
  -> 把 capability 解析为候选工具
  -> 调用选定工具
  -> 记录 tool call 和 result
  -> 把 ToolObservation 返回给 agent stage

ScientificAgent
  -> 根据 profile 和 schema 解释 observation
  -> 生成下一步结构化科学结果
```

这种分离很重要，因为工具调用会影响 safety、cost、reproducibility、memory、graph state 和未来训练数据。

## 模型路由

不同 agent 或 stage 可以使用不同模型，但模型选择不应该硬编码在学科子类里。

推荐设计：

```text
ModelRuntimeResolver
  inputs:
    stage
    discipline profile
    task adapter
    complexity estimate
    budget policy
    latency policy
    required tool use
    required reasoning quality

  output:
    model choice
    reasoning effort
    temperature policy
    fallback model
    budget guardrails
```

例子：

- 文献初筛可以使用更便宜的模型。
- 假说批判可以使用更强推理模型。
- formal review record 可以使用更严格、低随机性的设置。
- 工具规划可以使用 tool calling 能力更强的模型。
- 长上下文综合可以使用长上下文模型。

## Memory 和 Graph 治理

Memory 和 graph 写入应该由 runtime 治理，而不是由 agent 直接拥有。

推荐流程：

```text
agent output
  -> proposed memory diff
  -> proposed graph diff
  -> runtime validation
  -> scope routing
  -> conflict/staleness checks
  -> write log
  -> recall index update
```

Memory scope 应该保持显式：

- Personal memory。
- Group memory。
- Project memory。
- Local/session memory。
- Literature digest/wiki。
- Failed attempts memory。

当 memory 在不同 scope 之间迁移时，runtime 应该记录 migration log。自动 memory 迁移是可以允许的，但必须受 policy 控制、可审计、可回滚。

## 文献组织方式

文献层应该结合 raw source preservation 和 digest-first synthesis。

推荐层次：

```text
raw sources
  -> 不可变的 paper、competition doc、dataset、note

source digests
  -> 每个 source 一个 digest
  -> claims、methods、evidence、limitations、quality assessment

synthesis pages
  -> topic summaries
  -> claim tables
  -> conflict maps
  -> citation graph summaries

decision-linked evidence
  -> evidence object 连接到 hypothesis、failure 和 next action
```

对于完全自主科研，可以在 policy 允许下自动从 digest 更新 wiki。对于交互式科研，可以要求用户确认 digest 之后，再更新持久 synthesis page。

## 多智能体协作

多智能体协作应该由 director 协调，而不是隐藏在单个 agent 内部。

推荐角色：

- 文献 reviewer。
- 假说 proposer。
- 怀疑型 reviewer。
- 实验 designer。
- 证据 analyst。
- 可复现性 reviewer。
- 安全 reviewer。
- 领域 specialist。
- 组会 chair。

每个角色可以共享同一个生命周期骨架，但使用不同的 role prompt、memory view、quality gate 和 decision responsibility。

角色 memory 和 stance continuity 应该被记录下来，避免 reviewer 每一轮都重置立场。

## Evaluation 和 Learning 层

Kaivu 应该把科研业务逻辑和 learning substrate 分开。

Learning 层应该记录：

- Episode。
- Trajectory。
- Tool call。
- Model call。
- Context snapshot。
- Memory diff。
- Graph diff。
- Artifact provenance。
- Evaluation score。
- Human feedback。
- Decision outcome。

当前用途：

- Observability。
- Replay。
- Benchmark。
- Regression testing。
- Data accumulation。

未来用途：

- 单智能体 policy optimization。
- 多智能体 coordination optimization。
- Reward modeling。
- Preference learning。
- Agentic reinforcement learning。

## Kaggle 的设计含义

Kaggle 不应该从一开始就被设计成一条独立的科学 workflow。

推荐结构：

```text
ScientificAgent
  + ArtificialIntelligence DisciplineProfile
  + KaggleTaskAdapter
  + KaggleCapabilityPack
  + KaggleExecutionEnvironment
```

Kaggle-specific logic 主要属于：

- 从 competition description 进行 problem framing。
- 解析 dataset 和 metric。
- 检查 leakage 和 validation。
- 构建 baseline。
- feature engineering 和 modeling loop。
- experiment scheduler。
- submission dry-run。
- leaderboard risk interpretation。

这样 Kaggle 可以复用统一科研生命周期，同时专门化任务语义。

## 确认后的迁移计划

如果这份设计确认通过，代码重构应该小步进行：

1. 引入 `DisciplineProfile`、`TaskAdapter`、`StagePlan` 和 `StageExecutionMode` 数据结构，不改变当前行为。
2. 把 prompt 差异、failure taxonomy、quality gate 和 capability preference 从子类方法迁移到 profile。
3. 让 `ScientificAgent` 根据 profile、task adapter、context 和 schema 构建生命周期 stage request。
4. 让 `ScientificAgentRuntime` 通过 capability registry、tool policy、memory governance、graph governance 和 episode recording 执行 stage plan。
5. 让现有 discipline agent 变薄，只保留无法声明式表达的硬行为覆写。
6. 把 Kaggle 重构为 `ArtificialIntelligence profile + KaggleTaskAdapter + Kaggle capability pack + Kaggle environment`。
7. 增加 lifecycle stage planning、capability resolution、memory/graph write governance 和 Kaggle task adaptation 的回归测试。
8. 等代码结构稳定后，再更新 README 和 architecture docs。

## 非目标

这个设计刻意避免：

- 每个学科一套独立 workflow class。
- 为 prompt-only 差异建立大型继承树。
- scientific agent object 直接调用工具。
- scientific agent object 直接写 memory 或 graph。
- 把 Kaggle 当成和 AI research 无关的东西。
- 把大模型只当成文本生成器，而不是主要科学推理引擎。

## 待确认问题

重写代码之前，需要确认几个关键设计问题：

- `DisciplineProfile` 应该是纯 Python dataclass，还是 YAML 文件，还是两者都支持。
- stage prompt 应该放在代码里、markdown prompt 文件里，还是 profile 配置里。
- 交互式确认应该按 memory scope 控制，按 task mode 控制，还是按 lifecycle stage 控制。
- `TaskAdapter` 只负责 normalized input，还是也负责生成 stage-specific prompt fragment。
- 第一轮重构应该只针对 AI/Kaggle，还是同时覆盖所有学科。

## 总结

最重要的架构变化，不是增加更多子类，而是让 Kaivu 变成 profile-driven、schema-driven、capability-driven 和 runtime-governed 的系统。

base agent 定义生命周期。profile 表达学科科学风格。task adapter 表达任务约束。runtime 控制工具、memory、graph、execution 和 trajectory。director 负责项目和团队层面的科研协调。

这样 Kaivu 才能拥有稳定的科学内核，同时不会把科学推理僵硬地写死在 workflow 代码里。
