<script lang="ts">
  import { Cart } from "../lib/cart";

  let cart: Cart = new Cart();
</script>

<div>{cart.total()}</div>
