<script lang="ts">
  // A component is a class in the model too, but it extends nothing, so the
  // rule never matches it.
  let { title }: { title: string } = $props();
</script>

<h1>{title}</h1>
