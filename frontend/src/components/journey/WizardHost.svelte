<script lang="ts">
  // Renders the wizard that is open. A page opens one with `openWizard`.
  import type { ProjectInfo, XmiInfo } from "../../lib/api";
  import AcceptCodeWizard from "./AcceptCodeWizard.svelte";
  import AutomateWizard from "./AutomateWizard.svelte";
  import RuleWizard from "./RuleWizard.svelte";
  import TagWizard from "./TagWizard.svelte";
  import { wizards } from "./wizards.svelte";

  let {
    project,
    xmi,
    onParsed,
    onShow,
  }: {
    project: ProjectInfo;
    xmi: XmiInfo | null;
    /** A wizard parsed the code again. */
    onParsed: (x: XmiInfo) => void;
    /** A wizard asks for the code against the reference on the diagram page. */
    onShow: () => void;
  } = $props();

  const spec = $derived(wizards.active);
</script>

{#if spec?.kind === "rule"}
  {#key spec}<RuleWizard {project} {xmi} type={spec.type} />{/key}
{:else if spec?.kind === "edit-rule"}
  <RuleWizard {project} {xmi} edit={spec.rule} />
{:else if spec?.kind === "tag" && xmi}
  <TagWizard {project} {xmi} tag={spec.tag} {onParsed} />
{:else if spec?.kind === "accept-code"}
  <AcceptCodeWizard {project} {onShow} />
{:else if spec?.kind === "automate"}
  <AutomateWizard {project} />
{/if}
