<script lang="ts">
  import PriceTag from "./PriceTag.svelte";
  import type { Book } from "../lib/catalog";

  let { book, onAdd }: { book: Book; onAdd: (book: Book) => void } = $props();

  let available = $derived(book.isAvailable());

  function add(): void {
    if (available) onAdd(book);
  }
</script>

<article class="book">
  <h3>{book.title}</h3>
  <p>by {book.author.name} ({book.author.country})</p>
  <PriceTag amount={book.price} />
  {#if available}
    <button onclick={add}>Add to cart</button>
  {:else}
    <span class="oos">Out of stock</span>
  {/if}
</article>

<style>
  .book { border: 1px solid #ddd; padding: 0.75rem; border-radius: 6px; }
  .oos { color: #888; font-style: italic; }
</style>
