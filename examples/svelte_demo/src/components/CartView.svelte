<script lang="ts">
  import PriceTag from "./PriceTag.svelte";
  import { Cart } from "../lib/cart";

  let { cart }: { cart: Cart } = $props();
  let total = $derived(cart.total());

  function removeLine(title: string): void {
    cart.remove(title);
  }
</script>

<section class="cart">
  <h2>Your cart</h2>
  {#if cart.lines.length === 0}
    <p class="empty">No items yet.</p>
  {:else}
    <ul>
      {#each cart.lines as line}
        <li>
          {line.quantity} × {line.book.title}
          <PriceTag amount={line.book.price * line.quantity} />
          <button onclick={() => removeLine(line.book.title)}>Remove</button>
        </li>
      {/each}
    </ul>
    <p class="total">Total: <PriceTag amount={total} /></p>
  {/if}
</section>

<style>
  .cart { padding: 0.75rem; }
  .total { margin-top: 0.5rem; font-weight: 600; }
  .empty { color: #888; }
</style>
