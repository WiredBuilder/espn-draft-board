// Paste into the browser console (or run via a browser automation tool) on the
// ESPN draft room tab with the Activity panel set to "Picks". It reads the
// pick list and prints one name per line, ready for taken.txt. Your own picks
// are prefixed with "* " (edit MY_TEAM). It clicks nothing.
const MY_TEAM = 'Your Team Name';
const lines = (document.querySelector('.draft-columns')?.lastElementChild?.innerText || '').split('\n');
const out = [];
for (let i = 1; i < lines.length; i++) {
  const m = lines[i].match(/^R(\d+), P(\d+) - (.+)$/);
  if (m) out.push((m[3].includes(MY_TEAM) ? '* ' : '') + lines[i - 1].split(' / ')[0].trim());
}
out.join('\n');
