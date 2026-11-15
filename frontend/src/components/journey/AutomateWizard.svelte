<script lang="ts">
  // Run the check with no person in the loop: in CI, before a commit, and from
  // a coding agent. The texts are the ones of docs/TUTORIAL.md part 9 and of
  // the README. Change them there too.
  import { api, type ProjectInfo } from "../../lib/api";
  import CopyBlock from "./CopyBlock.svelte";
  import Wizard, { type NextAction } from "./Wizard.svelte";
  import { closeWizard } from "./wizards.svelte";

  let { project }: { project: ProjectInfo } = $props();

  const steps = ["Continuous integration", "Before each commit", "Coding agents"];
  let step = $state(0);
  let ci = $state<"github" | "gitlab" | "script">("github");
  let notice = $state("");

  const GITHUB = `# .github/workflows/architecture.yml
name: architecture
on: [pull_request]

jobs:
  constraints:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0            # \`--base-ref\` needs history

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install code-constraints

      - name: Architectural constraints
        run: cdec check --base-ref origin/\${{ github.base_ref }} --json-out report.json

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: constraint-report
          path: report.json`;

  const GITLAB = `# .gitlab-ci.yml
architecture:
  image: python:3.12
  script:
    - pip install code-constraints
    - cdec check --base-ref origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME --json-out report.json
  artifacts:
    when: always
    paths: [report.json]`;

  const PRE_COMMIT = `# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: cdec-check
        name: cdec check
        entry: cdec check
        language: system
        pass_filenames: false`;

  const HCM = `npm install -g harness-config-manager
cdec hcm init
hcm install code-constraints -t claude-code`;

  const MCP = `{
  "mcpServers": {
    "code-constraints": { "type": "stdio", "command": "cdec-mcp", "args": [] }
  }
}`;

  async function writeScripts() {
    try {
      const done = await api.writeCiScripts(project.id);
      notice = `Wrote ${done.written.join(" and ")}.`;
    } catch (e) {
      notice = (e as Error).message;
    }
  }

  const next = $derived<NextAction | null>(step < 2 ? { label: "Next" } : null);
</script>

<Wizard title="Run the check automatically" {steps} bind:step {next} onclose={() => closeWizard()}>
  {#if step === 0}
    <p class="muted">
      One command is the whole gate: <code>cdec check</code>. It exits with code 1 when an issue
      is open. CI needs the committed <code>.cdec/</code> folder and nothing else.
    </p>
    <div class="row" role="group" aria-label="CI system">
      <button class:primary={ci === "github"} onclick={() => (ci = "github")}>GitHub Actions</button>
      <button class:primary={ci === "gitlab"} onclick={() => (ci = "gitlab")}>GitLab CI</button>
      <button class:primary={ci === "script"} onclick={() => (ci = "script")}>A script</button>
    </div>
    {#if ci === "github"}
      <CopyBlock text={GITHUB} />
    {:else if ci === "gitlab"}
      <CopyBlock text={GITLAB} />
    {:else}
      <p>
        cdec writes <code>cdec-ci.sh</code> and <code>cdec-ci.bat</code> into the project root.
        Call the script from any CI system.
      </p>
      <button onclick={writeScripts}>Write the two scripts</button>
      {#if notice}<p class="muted" role="status">{notice}</p>{/if}
    {/if}
    <p class="muted">
      <code>--base-ref</code> compares a pull request with its target branch. Without it, the
      check compares with <code>.cdec/reference.xmi</code>.
    </p>
  {:else if step === 1}
    <p class="muted">
      A pre-commit hook finds an issue before it reaches CI. This uses
      <a href="https://pre-commit.com" target="_blank" rel="noreferrer">pre-commit</a>.
    </p>
    <CopyBlock text={PRE_COMMIT} />
  {:else}
    <p class="muted">
      A coding agent works inside the rules when it can read them and run the check.
    </p>
    <h3>Skills for the agent</h3>
    <p>
      The bundle teaches an agent to plan a design first, to add rules, and to act on a failed
      check. Run this in the project root:
    </p>
    <CopyBlock text={HCM} />
    <h3>The check as a tool (MCP)</h3>
    <p>
      Install the extra with <code>pip install "code-constraints[mcp]"</code>. Then put this in
      <code>.mcp.json</code> in the project root:
    </p>
    <CopyBlock text={MCP} />
  {/if}
</Wizard>
