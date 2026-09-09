<script lang="ts">
  import OrderRow from "../orders/OrderRow.svelte";

  let { title }: { title: string } = $props();
</script>

<!-- catalog -> orders. Rendering a child component is the edge a Svelte
     project actually has: the parser records the child as an attribute
     typed with the child's qualified name. -->
<div>
  {title}
  <OrderRow id="x" />
</div>
