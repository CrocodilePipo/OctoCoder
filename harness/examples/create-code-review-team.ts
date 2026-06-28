import { CodeReviewManager } from "../src/code-review/manager.js";
import { TeamManager } from "../src/teams/team.js";
import { ReviewSession } from "../src/code-review/session.js";

async function createThreePersonTeam() {
  const workDir = process.cwd();
  const teamManager = new TeamManager(workDir);
  const manager = new CodeReviewManager(workDir, teamManager);
  const session = new ReviewSession(workDir, manager);

  // Create a 3-person code review team
  const team = manager.createTeam("security-review-team", [
    {
      name: "alice",
      email: "alice@company.com",
      role: "lead",
      expertise: ["security", "architecture", "performance"]
    },
    {
      name: "bob", 
      email: "bob@company.com",
      role: "reviewer",
      expertise: ["testing", "code-quality", "documentation"]
    },
    {
      name: "charlie",
      email: "charlie@company.com", 
      role: "reviewer",
      expertise: ["typescript", "backend", "api-security"]
    }
  ]);

  console.log("✅ Created 3-person code review team:");
  console.log(`   Team Name: ${team.name}`);
  console.log(`   Created: ${new Date(team.createdAt).toLocaleString()}`);
  console.log("\n👥 Team Members:");
  
  team.members.forEach((member, index) => {
    const status = member.active ? "✅ Active" : "❌ Inactive";
    console.log(`   ${index + 1}. ${member.name} (${member.role})`);
    console.log(`      Email: ${member.email}`);
    console.log(`      Expertise: ${member.expertise.join(", ")}`);
    console.log(`      Status: ${status}`);
  });

  // Show team status
  console.log("\n📊 Team Status:");
  console.log(manager.getTeamSummary("security-review-team"));

  // Create a sample review request
  const request = session.createReviewRequest(
    "security-review-team",
    "Fix authentication vulnerability",
    "Implement secure password hashing and session management",
    "developer-john",
    "feature/security-fix",
    ["src/auth/password.ts", "src/auth/session.ts"]
  );

  console.log("\n🎯 Sample Review Request Created:");
  console.log(`   Request ID: ${request.id}`);
  console.log(`   Title: ${request.title}`);
  console.log(`   Author: ${request.author}`);
  console.log(`   Branch: ${request.branch}`);
  console.log(`   Reviewers: ${request.reviewers.join(", ")}`);
  console.log(`   Status: ${request.status}`);

  // Add some sample comments
  const comment1 = session.addComment(
    request.id,
    "alice",
    "Use bcrypt with cost factor 12 for password hashing",
    "src/auth/password.ts",
    45
  );

  const comment2 = session.addComment(
    request.id,
    "bob", 
    "Add unit tests for session timeout logic",
    "src/auth/session.ts",
    78
  );

  const comment3 = session.addComment(
    request.id,
    "charlie",
    "Consider implementing CSRF protection for session cookies",
    "src/auth/session.ts",
    23
  );

  console.log("\n💬 Sample Comments Added:");
  console.log(`   Total Comments: ${request.comments.length}`);
  
  // List all teams
  console.log("\n📋 All Available Teams:");
  const allTeams = manager.listTeams();
  allTeams.forEach(t => {
    const activeMembers = t.members.filter(m => m.active).length;
    console.log(`   • ${t.name} (${activeMembers}/${t.members.length} active members)`);
  });

  // Generate final report
  session.acceptComment(request.id, comment1.id, "Will implement bcrypt with cost factor 12");
  session.acceptComment(request.id, comment2.id, "Adding comprehensive unit tests now");
  session.rejectComment(request.id, comment3.id, "CSRF protection already implemented in middleware");

  const summary = session.generateFinalReport(request.id);
  console.log("\n📈 Review Summary:");
  console.log(`   Total Comments: ${summary.totalComments}`);
  console.log(`   Accepted: ${summary.acceptedSuggestions}`);
  console.log(`   Rejected: ${summary.rejectedSuggestions}`);
  console.log(`   Overall Conclusion: ${summary.overallConclusion.toUpperCase()}`);

  console.log("\n✨ 3-person code review team setup complete!");
}

createThreePersonTeam().catch(console.error);