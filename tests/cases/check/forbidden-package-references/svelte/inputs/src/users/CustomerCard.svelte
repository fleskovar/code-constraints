<script lang="ts">
  let { email }: { email: string } = $props();
</script>

<!-- In `to:` but never rendered from catalog. -->
<div>{email}</div>
