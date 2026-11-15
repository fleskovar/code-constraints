<script lang="ts">
  // A block of text to paste somewhere else, with a Copy button.
  let { text, label = "Copy" }: { text: string; label?: string } = $props();
  let copied = $state(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
      setTimeout(() => (copied = false), 1500);
    } catch {
      // No clipboard permission. The text is on the page: the user selects it.
    }
  }
</script>

<div class="copy-block">
  <pre>{text}</pre>
  <button onclick={copy}>{copied ? "Copied" : label}</button>
</div>

<style>
  .copy-block {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
  }
  pre {
    flex: 1;
    min-width: 0;
  }
  button {
    margin-top: 0.4rem;
    white-space: nowrap;
  }
</style>
