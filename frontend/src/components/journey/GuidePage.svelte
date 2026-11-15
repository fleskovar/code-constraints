<script lang="ts">
  // The project page: the codebase, the parts of the project, the one step
  // that is next, and every task. A project with no `.cdec/` chooses its
  // journey here. A greenfield project draws the
  // target first; a brownfield project records the code first.
  import "./journey.css";
  import {
    api,
    type GitInfo,
    type Journey,
    type JourneyStatus,
    type ProjectInfo,
    type XmiInfo,
  } from "../../lib/api";
  import { count } from "./text";
  import { openWizard, wizards } from "./wizards.svelte";

  export type GuideTarget = "diagram" | "edit" | "rules" | "checks" | "history";

  let {
    project,
    xmi,
    status = $bindable(),
    onGo,
  }: {
    project: ProjectInfo;
    xmi: XmiInfo | null;
    status: JourneyStatus | null;
    onGo: (target: GuideTarget) => void;
  } = $props();

  let error = $state("");
  let busy = $state(false);
  let classCount = $state<number | null>(null);
  let git = $state<GitInfo | null>(null);
  $effect(() => {
    api.gitInfo(project.id).then((g) => (git = g)).catch(() => (git = null));
  });
  // The choice of the user. Until then, the suggestion from the class count.
  let picked = $state<Journey | null>(null);
  const journey = $derived<Journey>(
    picked ?? (status?.journey || (classCount === 0 ? "greenfield" : "brownfield")),
  );

  $effect(() => {
    void wizards.done; // a wizard changed the project: read the status again
    api.journey(project.id).then((s) => (status = s)).catch((e: Error) => (error = e.message));
  });

  async function migrate() {
    try {
      status = await api.migrate(project.id);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  // Every task that a person brings to cdec. Each one opens a wizard or the
  // page that does it.
  const TASKS: { title: string; text: string; run: () => void }[] = [
    {
      title: "See why the check fails",
      text: "Run the check. Read each open issue, then fix it or accept it with a reason.",
      run: () => onGo("checks"),
    },
    {
      title: "Add a rule",
      text: "Choose a rule, fill in a form, and see what it reports before you turn it on.",
      run: () => openWizard({ kind: "rule" }),
    },
    {
      title: "Put a constraint on a class",
      text: "A tag in the code: sealed, immutable, a layer, a factory. The wizard gives the line to paste.",
      run: () => openWizard({ kind: "tag" }),
    },
    {
      title: "Plan a change",
      text: "Edit a copy of the diagram until it shows the target. Then set it as the goal.",
      run: () => onGo("edit"),
    },
    {
      title: "See how far the code is from the goal",
      text: "The timeline shows the code of today against the goal, and each recorded step.",
      run: () => onGo("history"),
    },
    {
      title: "Accept the code as the reference",
      text: "A change is complete and approved. The reference becomes the code of today.",
      run: () => openWizard({ kind: "accept-code" }),
    },
    {
      title: "Freeze an implementation",
      text: "Lock the body of a class or a function. The check fails when it changes.",
      run: () => openWizard({ kind: "tag", tag: "locked" }),
    },
    {
      title: "Check a plan or an older state",
      text: "Run the rules on the target model, or compare the code with a snapshot or a git revision.",
      run: () => onGo("checks"),
    },
    {
      title: "Review the accepted issues",
      text: "Withdraw an accepted issue, and remove the stale ones.",
      run: () => onGo("checks"),
    },
    {
      title: "Run the check automatically",
      text: "CI, a pre-commit hook, and the setup for a coding agent.",
      run: () => openWizard({ kind: "automate" }),
    },
    {
      title: "Compare two models",
      text: "The code, the target, a step of the timeline, a git revision or a file: show one, or compare two.",
      run: () => onGo("diagram"),
    },
  ];
  $effect(() => {
    if (!xmi) return;
    // A base class from a library is a node of the graph, not a class of the project.
    api
      .classGraph(xmi.id)
      .then((g) => (classCount = g.nodes.filter((n) => n.kind !== "external").length))
      .catch(() => {});
  });

  async function setUp() {
    busy = true;
    error = "";
    try {
      status = await api.journeyInit(project.id, journey);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  interface Step {
    title: string;
    text: string;
    done: boolean | null; // null: a step with no state to read
    action?: { label: string; run: () => void };
    command?: string;
  }

  const steps = $derived.by<Step[]>(() => {
    const s = status;
    if (!s?.configured) return [];
    const record: Step = {
      title: "Record progress",
      text:
        "After a piece of work, record a checkpoint. The timeline keeps the model of that moment " +
        "and shows how far the code is from the goal.",
      done: s.checkpoints > 0,
      action: { label: "Open the timeline", run: () => onGo("history") },
      command: 'cdec history add "What changed" -m "Why"',
    };
    const gate: Step = {
      title: "Run the check on every change",
      text:
        "Put this command in CI or in a pre-commit hook. It fails only for issues that nobody accepted.",
      done: null,
      command: "cdec check",
    };
    const goal: Step = {
      title: journey === "greenfield" ? "Draw the target model" : "Set a goal",
      text:
        (journey === "greenfield"
          ? "Add the classes and the relations that you plan to build. "
          : "Edit a copy of the diagram until it shows the architecture that you want. ") +
        "Then select Set as goal. The source code does not change.",
      done: s.goals > 0,
      action: { label: "Edit the diagram", run: () => onGo("edit") },
    };
    const rules: Step = {
      title: journey === "greenfield" ? "Turn on the rules that keep the code in the plan" : "Turn on the first rule",
      text:
        journey === "greenfield"
          ? "Start with “No class outside the reference model” and with the layer rule. " +
            "Each rule shows what it reports before you turn it on."
          : "Each rule shows the issues of today before you turn it on. Accept them in the same step, " +
            "and the check fails only for new ones. Start with one dependency rule.",
      done: s.rules > 0,
      action: { label: "Add a rule", run: () => openWizard({ kind: "rule" }) },
    };
    const setup: Step = {
      title: journey === "greenfield" ? "Create the project config" : "Record the code as it is",
      text: `${s.config_dir} holds rules.yaml, the reference model and the start of the timeline.`,
      done: true,
    };
    return journey === "greenfield" ? [setup, goal, rules, record, gate] : [setup, rules, goal, record, gate];
  });
  const next = $derived(steps.findIndex((s) => s.done === false));
</script>

<div class="jy guide">
  {#if error}<p class="error" role="alert">{error}</p>{/if}

  <div class="card codebase">
    <div class="row">
      <h2>The codebase</h2>
      <code title={project.path}>{project.path}</code>
      <span class="badge">{project.lang}</span>
      {#if classCount !== null}
        <span class="badge">{count(classCount, "class", "classes")}</span>
      {/if}
    </div>
    <p class="muted">
      {#if git?.is_git}
        git: <strong>{git.branch ?? "(detached)"}</strong> <code>{git.head_short}</code>
        {git.head_subject}{git.is_dirty ? " · with changes that are not committed" : ""}
      {:else if git}
        This folder is not in a git repository. cdec works without git: the timeline keeps
        the snapshots.
      {/if}
    </p>
    <p class="muted">
      The diagrams show the code as it is on the disk. After a change in the code, select
      <strong>Re-parse</strong> at the top.
    </p>
  </div>

  {#if !status}
    <p class="muted">Loading…</p>
  {:else if status.error}
    <p class="error">{status.error}</p>
  {:else if !status.configured}
    <h2>Set up this project</h2>
    <p class="muted">
      This path has no <code>.cdec/</code> folder. Choose how you start. You can look at the
      diagram first: select <strong>Diagram</strong> at the top.
    </p>
    <div class="choices" role="radiogroup" aria-label="Journey">
      <button
        class="card choice"
        class:active={journey === "greenfield"}
        role="radio"
        aria-checked={journey === "greenfield"}
        onclick={() => (picked = "greenfield")}
      >
        <h3>Start a new design</h3>
        <p>
          The folder has little or no code. You draw the target model first. The rules then keep
          the code inside the plan while it grows.
        </p>
      </button>
      <button
        class="card choice"
        class:active={journey === "brownfield"}
        role="radio"
        aria-checked={journey === "brownfield"}
        onclick={() => (picked = "brownfield")}
      >
        <h3>Adopt an existing codebase</h3>
        <p>
          The code exists. You record it as it is, then turn rules on one at a time. Each rule
          accepts the issues of today, so the check fails only for new ones.
        </p>
      </button>
    </div>
    <p class="muted">
      {#if classCount !== null}
        This path has {count(classCount, "class", "classes")}.
      {/if}
      The next step writes <code>.cdec/rules.yaml</code> with no rule, a snapshot of the model
      in <code>.cdec/reference.xmi</code>, and the first entry of the history. No rule is on
      after this step, so <code>cdec check</code> passes.
    </p>
    <button class="primary" onclick={setUp} disabled={busy}>
      {busy ? "Working…" : "Create the project config"}
    </button>
  {:else}
    <h2>{journey === "greenfield" ? "New design" : "Adoption of an existing codebase"}</h2>
    <div class="tiles">
      <button class="card tile" onclick={() => onGo("diagram")}>
        <strong>Diagrams</strong>
        <span class="muted">The model of the code, the target, and each snapshot.</span>
        {#if status.goal}
          <span class="badge goal" title={status.goal.note}>Goal: {status.goal.title}</span>
        {:else}
          <span class="badge">No open goal</span>
        {/if}
      </button>
      <button class="card tile" onclick={() => onGo("rules")}>
        <strong>Rules</strong>
        <span class="muted">The rules, the constraint tags in the code, the locks.</span>
        <span class="badge">{count(status.rules, "rule")} on</span>
      </button>
      <button class="card tile" onclick={() => onGo("checks")}>
        <strong>Checks</strong>
        <span class="muted">What the rules report on the code, a plan or a snapshot.</span>
        <span class="badge">{count(status.exceptions, "accepted issue")}</span>
      </button>
      <button class="card tile" onclick={() => onGo("history")}>
        <strong>Timeline</strong>
        <span class="muted">The start, each goal, each checkpoint, each rule change.</span>
        <span class="badge">{count(status.history, "step")}</span>
      </button>
    </div>

    {#if status.legacy.length > 0}
      <p class="card">
        This project has files of an older cdec: <code>{status.legacy.join(", ")}</code>. They
        still work. Fold them into <code>rules.yaml</code>, so one file holds everything.
        <button onclick={migrate}>Fold them in</button>
      </p>
    {/if}

    {#if next >= 0}
      {@const step = steps[next]}
      <div class="card step next">
        <span class="mark" aria-hidden="true">{next + 1}</span>
        <div class="body">
          <h3>{step.title} <span class="badge goal">next step</span></h3>
          <p class="muted">{step.text}</p>
          {#if step.action}
            <button class="primary" onclick={step.action.run}>{step.action.label}</button>
          {/if}
        </div>
      </div>
    {/if}

    <h2 class="section">What do you want to do?</h2>
    <div class="tasks">
      {#each TASKS as task (task.title)}
        <button class="card task" onclick={task.run}>
          <strong>{task.title}</strong>
          <span class="muted">{task.text}</span>
        </button>
      {/each}
    </div>

    <h2 class="section">The steps of the journey</h2>
    <ol class="steps">
      {#each steps as step, i (step.title)}
        <li class="card step" class:next={i === next} class:done={step.done === true}>
          <span class="mark" aria-hidden="true">{step.done === true ? "✓" : i + 1}</span>
          <div class="body">
            <h3>
              {step.title}
              {#if step.done === true}<span class="badge good">done</span>{/if}
              {#if i === next}<span class="badge goal">next</span>{/if}
            </h3>
            <p class="muted">{step.text}</p>
            {#if step.command}<pre>{step.command}</pre>{/if}
            {#if step.action}
              {@const action = step.action}
              <button onclick={action.run}>{action.label}</button>
            {/if}
          </div>
        </li>
      {/each}
    </ol>
  {/if}
</div>

<style>
  .codebase {
    margin-bottom: 1rem;
  }
  .codebase h2 {
    margin: 0;
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
    gap: 0.6rem;
    margin: 0.6rem 0 1rem;
  }
  .tile {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.3rem;
    text-align: left;
  }
  .tile strong {
    font-size: 1rem;
  }
  .guide {
    max-width: 52rem;
    margin: 0 auto;
    padding: 1.25rem;
  }
  .choices {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin: 0.75rem 0;
  }
  .choice {
    text-align: left;
    font-size: 0.9rem;
  }
  .choice.active {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }
  .tiles {
    margin: 0.5rem 0 1rem;
  }
  .steps {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .step {
    display: flex;
    gap: 0.75rem;
  }
  .step.next {
    border-color: var(--accent);
  }
  .step.done {
    opacity: 0.75;
  }
  .mark {
    flex: 0 0 1.6rem;
    height: 1.6rem;
    border-radius: 50%;
    background: var(--hover);
    display: grid;
    place-items: center;
    font-size: 0.8rem;
    font-weight: 600;
  }
  .step.done .mark {
    background: #dcfce7;
    color: #166534;
  }
  .body {
    flex: 1;
    min-width: 0;
  }
  .section {
    margin-top: 1.5rem;
  }
  .tasks {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
    gap: 0.6rem;
    margin-top: 0.5rem;
  }
  .task {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    text-align: left;
  }
</style>
