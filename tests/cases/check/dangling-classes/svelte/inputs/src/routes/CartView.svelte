<script lang="ts">
  import { Cart } from "../lib/cart";

  // A route component: nothing in the project renders it, the router does.
  // Exempt because it is named in `entry_points:`.
  let cart: Cart = new Cart();
</script>

<div>{cart.total()}</div>
