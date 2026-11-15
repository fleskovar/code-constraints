/** `1 rule`, `2 rules`. Pass the plural when it is not the word plus `s`. */
export function count(n: number, word: string, plural = `${word}s`): string {
  return `${n} ${n === 1 ? word : plural}`;
}
