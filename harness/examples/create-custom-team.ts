import { CodeReviewManager } from "../src/code-review/manager.js";
import { TeamManager } from "../src/teams/team.js";
import { ReviewSession } from "../src/code-review/session.js";

async function createCustomThreePersonTeam() {
  const workDir = process.cwd();
  const teamManager = new TeamManager(workDir);
  const manager = new CodeReviewManager(workDir, teamManager);
  const session = new ReviewSession(workDir, manager);

  // Create a custom 3-person code review team
  const team = manager.createTeam("core-review-team", [
    {
      name: "alex",
      email: "alex@company.com",
      role: "lead",
      expertise: ["system-design", "security", "performance-optimization"]
    },
    {
      name: "taylor",
      email: "taylor@company.com",
      role: "reviewer", 
      expertise: ["unit-testing", "integration-testing", "code-quality"]
    },
    {
      name: "jordan",
      email: "jordan@company.com",
      role: "reviewer",
      expertise: ["typescript", "api-design", "error-handling"]
    }
  ]);

  console.log("✅ Created custom 3-person code review team:");
  console.log(`   Team Name: ${team.name}`);
  console.log(`   Created: ${new Date(team.createdAt).toLocaleString()}`);
  console.log("\n👥 Team Members:");
  
  team.members.forEach((member, index) => {
    const status = member.active ? "✅ Active" : "❌ Inactive";
    const roleIcon = member.role === "lead" ? "👑" : "🔍";
    console.log(`   ${index + 1}. ${roleIcon} ${member.name} (${member.role})`);
    console.log(`      Email: ${member.email}`);
    console.log(`      Expertise: ${member.expertise.join(", ")}`);
    console.log(`      Status: ${status}`);
  });

  // Show team status
  console.log("\n📊 Team Status:");
  console.log(manager.getTeamSummary("core-review-team"));

  // Create a review request for core functionality
  const request = session.createReviewRequest(
    "core-review-team",
    "Implement core user management system",
    "Add user registration, login, and profile management functionality",
    "developer-sarah",
    "feature/user-management",
    ["src/auth/user-manager.ts", "src/api/user-routes.ts"]
  );

  console.log("\n🎯 Core Review Request Created:");
  console.log(`   Request ID: ${request.id}`);
  console.log(`   Title: ${request.title}`);
  console.log(`   Author: ${request.author}`);
  console.log(`   Branch: ${request.branch}`);
  console.log(`   Reviewers: ${request.reviewers.join(", ")}`);
  console.log(`   Status: ${request.status}`);

  // Add review comments from each team member
  const alexComment = session.addComment(
    request.id,
    "alex",
    "Consider implementing rate limiting for login attempts to prevent brute force attacks",
    "src/auth/user-manager.ts",
    120
  );

  const taylorComment = session.addComment(
    request.id,
    "taylor", 
    "Add comprehensive unit tests for password validation logic",
    "src/auth/user-manager.ts",
    85
  );

  const jordanComment = session.addComment(
    request.id,
    "jordan",
    "Use TypeScript strict mode and ensure proper error types are defined",
    "src/api/user-routes.ts",
    45
  );

  console.log("\n💬 Review Comments Added:");
  console.log(`   Alex (Lead): Security-focused comment`);
  console.log(`   Taylor (Reviewer): Testing-focused comment`);
  console.log(`   Jordan (Reviewer): TypeScript-focused comment`);
  
  // Process some comments
  session.acceptComment(request.id, alexComment.id, "Implementing rate limiting with Redis");
  session.acceptComment(request.id, taylorComment.id, "Adding comprehensive test suite");
  session.rejectComment(request.id, jordanComment.id, "TypeScript strict mode already enabled");

  // Generate final report
  const summary = session.generateFinalReport(request.id);
  console.log("\n📈 Review Summary:");
  console.log(`   Total Comments: ${summary.totalComments}`);
  console.log(`   Accepted: ${summary.acceptedSuggestions}`);
  console.log(`   Rejected: ${summary.rejectedSuggestions}`);
  console.log(`   Overall Conclusion: ${summary.overallConclusion.toUpperCase()}`);

  console.log("\n🔧 Team Configuration:");
  console.log(`   Configuration saved to: .mewcode/code-review-teams.json`);
  console.log(`   Team can be managed via: /code-review commands`);
  
  console.log("\n✨ Custom 3-person code review team creation complete!");
  console.log("\n📋 Next Steps:");
  console.log("   1. Use /code-review status core-review-team to check team status");
  console.log("   2. Use /code-review request core-review-team to create new review requests");
  console.log("   3. Use /code-comment to add review comments");
  console.log("   4. Use /code-review report to generate final reports");
}

createCustomThreePersonTeam().catch(console.error);