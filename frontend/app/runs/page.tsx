import { RunForm } from "@/components/RunForm";

export default function RunsPage() {
  return (
    <main className="mx-auto flex h-full w-full max-w-2xl flex-col justify-center px-6 py-8">
      <h1 className="mb-1 text-xl font-semibold">What should the agent do?</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        It can call any of mcp-toolkit-ai&apos;s MCP servers as tools -- code search, SQL, GitHub
        issues, the local dev environment, and a Markdown knowledge base.
      </p>
      <RunForm />
    </main>
  );
}
