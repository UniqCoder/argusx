// Truncate a real wallet address for display only — never use the output of
// this function as a value sent back to the backend (it can't be traced).
export function truncateAddress(address: string, head = 6, tail = 4): string {
  if (address.length <= head + tail + 3) return address;
  return `${address.slice(0, head)}...${address.slice(-tail)}`;
}
