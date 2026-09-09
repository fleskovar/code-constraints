<script lang="ts">
  let { label, count = 0 } = $props();
</script>

<span class="badge">{label}: {count}</span>

<style>
  .badge { font-weight: bold; }
</style>
