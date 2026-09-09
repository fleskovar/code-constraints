<script lang="ts">
  import BookCard from "./BookCard.svelte";

  let { name }: { name: string } = $props();
</script>

<!-- catalog -> catalog. A self-edge is dropped before the rule sees it. -->
<div>
  {name}
  <BookCard title="y" />
</div>
