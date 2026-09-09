<script lang="ts">
  import Badge from "./Badge.svelte";
  import { Cart, type CartItem } from "../lib/store";

  let cart: Cart = new Cart();
  let count: number = $state(0);
  let total = $derived(cart.total());

  function addItem(item: CartItem): void {
    cart.add(item);
    count += 1;
  }
</script>

<div>
  <Badge label="items" {count} />
  {#if count > 0}
    <Badge label="total" count={total} />
  {/if}
  <button onclick={() => addItem({ id: "x", price: 1 })}>Add</button>
</div>
