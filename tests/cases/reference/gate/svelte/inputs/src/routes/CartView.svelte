<script lang="ts">
  import { Cart } from "../lib/cart";

  let cart: Cart = new Cart();
  let count: number = $state(0);
</script>

<div>{cart.total(2)} {count}</div>
