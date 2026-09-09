/** User hierarchy: abstract User with Customer / Admin specialisations. */
import { Notification } from "../notifications/base";

export abstract class User {
  email: string;
  name: string;

  constructor(email: string, name: string) {
    this.email = email;
    this.name = name;
  }

  abstract role(): string;
}

export class Customer extends User {
  notifier: Notification;
  address: string;

  constructor(email: string, name: string, notifier: Notification) {
    super(email, name);
    this.notifier = notifier;
    this.address = "";
  }

  role(): string {
    return "customer";
  }

  charge(amount: number): boolean {
    return amount > 0;
  }
}

export class Admin extends User {
  level: number;

  constructor(email: string, name: string, level: number = 1) {
    super(email, name);
    this.level = level;
  }

  role(): string {
    return "admin";
  }
}
