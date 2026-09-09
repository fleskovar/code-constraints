class OrderController(BaseCommand):
    """No incoming references either, but it derives from a configured
    framework base, so the framework is assumed to instantiate it."""

    def run(self) -> None:
        pass
