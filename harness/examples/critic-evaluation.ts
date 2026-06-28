import { CodeReviewManager } from "../src/code-review/manager.js";
import { TeamManager } from "../src/teams/team.js";
import { ReviewSession } from "../src/code-review/session.js";

async function criticEvaluation() {
  const workDir = process.cwd();
  const teamManager = new TeamManager(workDir);
  const manager = new CodeReviewManager(workDir, teamManager);
  const session = new ReviewSession(workDir, manager);

  // First, ensure we have the security-review-team with a critic
  console.log("🔍 Setting up security-review-team with critic member...");
  
  try {
    manager.addMember("security-review-team", {
      name: "david",
      email: "david@company.com",
      role: "critic",
      expertise: ["code-review", "quality-assurance", "architecture-review", "security-audit"]
    });
    console.log("✅ Added david as critic");
  } catch (error) {
    console.log("ℹ️ David already exists as critic member");
  }

  // Create a new review request
  const request = session.createReviewRequest(
    "security-review-team",
    "Review src/agent/agent.ts code quality",
    "Please review the Agent class implementation for code quality, security, and best practices",
    "developer-team",
    "main",
    ["src/agent/agent.ts"]
  );

  console.log(`\n🎯 Created Review Request: ${request.id}`);
  console.log(`   Title: ${request.title}`);
  console.log(`   Reviewers: ${request.reviewers.join(", ")}`);

  // Bob (Reviewer 1) adds comments
  console.log("\n👤 Bob (Reviewer) adding code quality comments:");

  const bobComments = [];
  
  bobComments.push(session.addComment(
    request.id,
    "bob",
    "代码质量评价：整体结构清晰，但缺少错误处理的边界情况测试。建议为 executeTools 方法添加单元测试，特别是针对权限检查失败、hook 拒绝、工具执行超时等场景。",
    "src/agent/agent.ts",
    135
  ));

  bobComments.push(session.addComment(
    request.id,
    "bob",
    "改进建议1：在 run() 方法中添加更详细的错误处理日志。当前 catch 块只是简单地 yield error，建议记录错误上下文信息（如当前工具、参数、状态）以便调试。",
    "src/agent/agent.ts",
    102
  ));

  bobComments.push(session.addComment(
    request.id,
    "bob",
    "改进建议2：为 AgentConfig 接口添加 JSDoc 注释，说明每个配置项的作用和默认值。特别是 onPermissionRequest 回调的返回值含义需要文档说明。",
    "src/agent/agent.ts",
    9
  ));

  bobComments.push(session.addComment(
    request.id,
    "bob",
    "改进建议3：考虑添加配置验证机制，在构造函数中验证必需的配置项（如 client、registry、conversation）是否存在，避免运行时出现 undefined 错误。",
    "src/agent/agent.ts",
    33
  ));

  // Charlie (Reviewer 2) adds comments
  console.log("👤 Charlie (Reviewer) adding technical comments:");

  const charlieComments = [];

  charlieComments.push(session.addComment(
    request.id,
    "charlie",
    "代码质量评价：TypeScript 类型使用良好，但存在一些潜在的类型安全问题。toolSchemas 在循环外获取，如果工具注册表在运行时动态变化，可能导致 schema 不一致。",
    "src/agent/agent.ts",
    44
  ));

  charlieComments.push(session.addComment(
    request.id,
    "charlie",
    "改进建议1：将 toolSchemas 的获取移到工具执行前，或者添加缓存失效机制。考虑在工具执行时动态获取最新的 schema，确保与实际可用工具保持同步。",
    "src/agent/agent.ts",
    44
  ));

  charlieComments.push(session.addComment(
    request.id,
    "charlie",
    "改进建议2：在 executeTools 方法中添加工具执行超时控制。当前没有超时机制，恶意或卡死的工具可能导致整个 Agent 循环阻塞。建议为每个工具执行设置合理的超时时间。",
    "src/agent/agent.ts",
    135
  ));

  charlieComments.push(session.addComment(
    request.id,
    "charlie",
    "改进建议3：增强安全性，对 toolName 和 arguments 进行输入验证和清理。虽然 PermissionChecker 已经处理了大部分安全问题，但建议在工具执行前添加额外的参数类型验证，防止类型混淆攻击。",
    "src/agent/agent.ts",
    160
  ));

  charlieComments.push(session.addComment(
    request.id,
    "charlie",
    "安全建议：在权限检查通过后，工具执行前，建议添加操作审计日志。记录谁在什么时间执行了什么工具，这对安全审计和问题追踪很重要。",
    "src/agent/agent.ts",
    177
  ));

  console.log(`\n📝 Total Comments Added: ${bobComments.length + charlieComments.length}`);

  // David (Critic) evaluates each comment
  console.log("\n👤 David (Critic) evaluating reviewer suggestions...");
  console.log("═══════════════════════════════════════════════════");

  // Evaluate Bob's comments
  console.log("\n📋 Bob's Comments Evaluation:");
  console.log("─────────────────────────────────");

  const evaluations = [];

  // Comment 1: Unit testing suggestion
  console.log("\n1️⃣  [Bob] 单元测试建议");
  console.log("   建议: 整体结构清晰，但缺少错误处理的边界情况测试...");
  const eval1 = session.addCriticAssessment(
    request.id,
    bobComments[0].id,
    "david",
    "reasonable",
    "✅ 合理：单元测试对代码质量至关重要。executeTools 方法涉及权限检查、hook 触发、工具执行等多个复杂流程，确实需要全面的单元测试覆盖。作者关于'单独测试文件'的回应不够充分，核心逻辑测试应该在对应模块的测试文件中进行。"
  );
  evaluations.push(eval1);
  console.log(`   评估: ${eval1.evaluation.toUpperCase()}`);
  console.log(`   理由: 单元测试是质量保障的基础，复杂逻辑必须有测试覆盖`);

  // Comment 2: Error handling logs
  console.log("\n2️⃣  [Bob] 错误处理日志建议");
  console.log("   建议: 在 run() 方法中添加更详细的错误处理日志...");
  const eval2 = session.addCriticAssessment(
    request.id,
    bobComments[1].id,
    "david",
    "reasonable",
    "✅ 合理：错误处理日志是生产环境调试的关键。当前的简单错误 yield 无法提供足够的上下文信息，特别是在分布式或异步环境中。详细的错误上下文（工具名、参数、执行状态）对于问题诊断和系统监控都很有价值。"
  );
  evaluations.push(eval2);
  console.log(`   评估: ${eval2.evaluation.toUpperCase()}`);
  console.log(`   理由: 详细的错误日志对生产环境的故障排查至关重要`);

  // Comment 3: JSDoc documentation
  console.log("\n3️⃣  [Bob] JSDoc 文档建议");
  console.log("   建议: 为 AgentConfig 接口添加 JSDoc 注释...");
  const eval3 = session.addCriticAssessment(
    request.id,
    bobComments[2].id,
    "david",
    "reasonable",
    "✅ 合理：代码文档是维护成本的重要因素。AgentConfig 作为核心配置接口，缺乏清晰的文档会导致使用困难和维护问题。特别是 onPermissionRequest 这种回调机制，返回值的语义不同会导致完全不同的行为，必须有明确文档说明。"
  );
  evaluations.push(eval3);
  console.log(`   评估: ${eval3.evaluation.toUpperCase()}`);
  console.log(`   理由: 核心配置接口必须有清晰文档，回调机制尤其需要说明`);

  // Comment 4: Configuration validation
  console.log("\n4️⃣  [Bob] 配置验证建议");
  console.log("   建议: 考虑添加配置验证机制...");
  const eval4 = session.addCriticAssessment(
    request.id,
    bobComments[3].id,
    "david",
    "partially-reasonable",
    "⚠️  部分合理：TypeScript 编译时验证确实提供了基本保障，但运行时验证仍然有价值。特别是在插件系统或动态配置场景下，编译时类型检查无法覆盖所有情况。建议部分接受：在关键路径添加防御性检查，但避免过度验证影响性能。"
  );
  evaluations.push(eval4);
  console.log(`   评估: ${eval4.evaluation.toUpperCase()}`);
  console.log(`   理由: 编译时验证不能完全替代运行时检查，但需要平衡性能`);

  // Evaluate Charlie's comments
  console.log("\n📋 Charlie's Comments Evaluation:");
  console.log("─────────────────────────────────");

  // Comment 5: Type safety with toolSchemas
  console.log("\n5️⃣  [Charlie] Schema 类型安全建议");
  console.log("   建议: TypeScript 类型使用良好，但存在潜在类型安全问题...");
  const eval5 = session.addCriticAssessment(
    request.id,
    charlieComments[0].id,
    "david",
    "unreasonable",
    "❌ 不合理：这个担忧过度了。toolSchemas 在每次 run() 调用开始时获取，而 Agent 的生命周期通常是单次会话。在正常使用场景下，工具注册表不会在 Agent 运行过程中动态变化。如果确实存在这种需求，应该通过架构层面解决，而不是在这个层面添加复杂性。"
  );
  evaluations.push(eval5);
  console.log(`   评估: ${eval5.evaluation.toUpperCase()}`);
  console.log(`   理由: 过度担忧，工具注册表在 Agent 生命周期中不会动态变化`);

  // Comment 6: Dynamic schema retrieval
  console.log("\n6️⃣  [Charlie] 动态 Schema 获取建议");
  console.log("   建议: 将 toolSchemas 的获取移到工具执行前...");
  const eval6 = session.addCriticAssessment(
    request.id,
    charlieComments[1].id,
    "david",
    "unreasonable",
    "❌ 不合理：与上一条建议存在矛盾。如果工具注册表不会动态变化，那么动态获取 schema 就没有必要，反而会增加性能开销。这种'为了安全而安全'的建议会增加系统复杂度而没有实际收益。应该坚持简单的设计原则。"
  );
  evaluations.push(eval6);
  console.log(`   评估: ${eval6.evaluation.toUpperCase()}`);
  console.log(`   理由: 与前一条建议矛盾，增加复杂度但无实际收益`);

  // Comment 7: Tool execution timeout
  console.log("\n7️⃣  [Charlie] 工具执行超时建议");
  console.log("   建议: 在 executeTools 方法中添加工具执行超时控制...");
  const eval7 = session.addCriticAssessment(
    request.id,
    charlieComments[2].id,
    "david",
    "reasonable",
    "✅ 合理：超时控制是系统稳定性的关键保障。没有超时机制的工具执行确实可能导致整个 Agent 循环阻塞，特别是在网络操作或外部 API 调用时。建议实现渐进式超时策略：首次调用较短超时，重试时逐渐延长，并考虑熔断机制。"
  );
  evaluations.push(eval7);
  console.log(`   评估: ${eval7.evaluation.toUpperCase()}`);
  console.log(`   理由: 超时控制是系统稳定性的基础，防止工具阻塞整个循环`);

  // Comment 8: Input validation and sanitization
  console.log("\n8️⃣  [Charlie] 输入验证建议");
  console.log("   建议: 增强安全性，对 toolName 和 arguments 进行输入验证...");
  const eval8 = session.addCriticAssessment(
    request.id,
    charlieComments[3].id,
    "david",
    "partially-reasonable",
    "⚠️  部分合理：虽然 PermissionChecker 确实提供了参数验证，但多层防御是安全最佳实践。建议在工具执行层添加轻量级的类型和格式验证，作为'安全网'机制。不过要避免过度验证导致的性能问题和维护负担。"
  );
  evaluations.push(eval8);
  console.log(`   评估: ${eval8.evaluation.toUpperCase()}`);
  console.log(`   理由: 多层防御是安全最佳实践，但需要平衡性能和维护成本`);

  // Comment 9: Security audit logging
  console.log("\n9️⃣  [Charlie] 安全审计日志建议");
  console.log("   建议: 在权限检查通过后，工具执行前，建议添加操作审计日志...");
  const eval9 = session.addCriticAssessment(
    request.id,
    charlieComments[4].id,
    "david",
    "reasonable",
    "✅ 合理：安全审计日志是不可妥协的安全要求。在 AI Agent 这种能够执行实际操作的系统中，记录每个工具执行的详细信息（操作者、时间、参数、结果）是合规性和安全追溯的基础。这不仅是安全最佳实践，在很多场景下是法律要求。"
  );
  evaluations.push(eval9);
  console.log(`   评估: ${eval9.evaluation.toUpperCase()}`);
  console.log(`   理由: AI Agent 系统必须具备完整的安全审计能力，这是合规性要求`);

  // Generate comprehensive critic summary
  console.log("\n📊 COMPREHENSIVE CRITIC EVALUATION SUMMARY");
  console.log("==========================================");
  
  const criticSummary = session.getCriticSummary(request.id);
  console.log(criticSummary);

  // Analysis statistics
  const reasonableCount = evaluations.filter(e => e.evaluation === "reasonable").length;
  const unreasonableCount = evaluations.filter(e => e.evaluation === "unreasonable").length;
  const partiallyReasonableCount = evaluations.filter(e => e.evaluation === "partially-reasonable").length;

  console.log("\n📈 EVALUATION STATISTICS");
  console.log("─────────────────────────────────");
  console.log(`✅ Reasonable:        ${reasonableCount}`);
  console.log(`❌ Unreasonable:      ${unreasonableCount}`);
  console.log(`⚠️  Partially Reasonable: ${partiallyReasonableCount}`);
  console.log(`📊 Reasonable Rate:  ${((reasonableCount + partiallyReasonableCount * 0.5) / evaluations.length * 100).toFixed(1)}%`);

  console.log("\n🎯 KEY INSIGHTS");
  console.log("─────────────────────────────────");
  console.log("• 5条建议完全合理，应该立即实施");
  console.log("• 2条建议存在过度设计问题，应该拒绝");
  console.log("• 2条建议部分合理，需要调整实施策略");
  console.log("• 整体审查质量较高，但需要避免'为了安全而安全'的倾向");

  console.log("\n✅ Critic evaluation completed!");
  console.log(`   David evaluated all ${evaluations.length} reviewer comments`);
  console.log("   Each evaluation includes detailed reasoning");
}

criticEvaluation().catch(console.error);