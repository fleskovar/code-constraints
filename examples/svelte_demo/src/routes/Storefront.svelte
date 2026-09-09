<script lang="ts">
  import BookCard from "../components/BookCard.svelte";
  import CartView from "../components/CartView.svelte";
  import { Author, Book } from "../lib/catalog";
  import { Cart } from "../lib/cart";

  const catalog: Book[] = [
    new Book("Dune", new Author("Frank Herbert", "US"), 12.5, 4),
    new Book("Solaris", new Author("Stanisław Lem", "PL"), 9.0, 0),
    new Book("Anathem", new Author("Neal Stephenson", "US"), 15.0, 2),
  ];

  let cart: Cart = $state(new Cart());
  let added: number = $state(0);

  function handleAdd(book: Book): void {
    if (cart.add(book, 1)) {
      added += 1;
    }
  }
</script>

<main>
  <h1>Bookstore</h1>
  <p>Items added so far: {added}</p>

  <div class="grid">
    {#each catalog as book}
      <BookCard {book} onAdd={handleAdd} />
    {/each}
  </div>

  <CartView {cart} />
</main>

<style>
  main { font-family: sans-serif; padding: 1rem; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
</style>
