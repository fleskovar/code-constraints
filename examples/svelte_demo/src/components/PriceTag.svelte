<script lang="ts">
  let { amount, currency = "USD" } = $props();
</script>

<span class="price">{currency} {amount.toFixed(2)}</span>

<style>
  .price { font-weight: 600; }
</style>
