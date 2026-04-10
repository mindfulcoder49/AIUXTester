const CARD_WIDTH = 248;
const CARD_HEIGHT = 132;
const COLUMN_GAP = 92;
const ROW_GAP = 30;

export function getBracketConstants() {
  return {
    cardWidth: CARD_WIDTH,
    cardHeight: CARD_HEIGHT,
    columnGap: COLUMN_GAP,
    rowGap: ROW_GAP,
  };
}

function makeMatches(ids) {
  if (ids.length === 1) return [ids];
  const matches = [];
  let start = 0;
  if (ids.length % 2 === 1) {
    matches.push([ids[0], ids[1], ids[2]]);
    start = 3;
  }
  for (let index = start; index < ids.length; index += 2) {
    matches.push([ids[index], ids[index + 1]]);
  }
  return matches;
}

export function buildPreviewRounds(entryIds) {
  const rounds = [];
  let currentIds = [...entryIds];
  let roundNumber = 1;

  while (currentIds.length > 1) {
    const matches = makeMatches(currentIds).map((ids, index) => ({
      id: `preview-r${roundNumber}-m${index + 1}`,
      round_number: roundNumber,
      match_number: index + 1,
      entry_ids_parsed: ids,
      entry_ids: JSON.stringify(ids),
      winner_entry_id: null,
      judge_reasoning: "",
      status: "pending",
    }));
    rounds.push(matches);
    currentIds = matches.map((match) => `winner-r${roundNumber}-m${match.match_number}`);
    roundNumber += 1;
  }

  return rounds;
}

export function buildBracketLayout(rounds) {
  if (!rounds.length) {
    return { columns: [], connectors: [], stageWidth: 0, stageHeight: 0 };
  }

  const columns = rounds.map(() => []);
  const firstRoundStep = CARD_HEIGHT + ROW_GAP;

  rounds[0].forEach((match, index) => {
    const top = index * firstRoundStep;
    columns[0].push({
      ...match,
      top,
      left: 0,
      width: CARD_WIDTH,
      height: CARD_HEIGHT,
      center: top + CARD_HEIGHT / 2,
      children: [],
    });
  });

  for (let roundIndex = 1; roundIndex < rounds.length; roundIndex += 1) {
    let childCursor = 0;
    const left = roundIndex * (CARD_WIDTH + COLUMN_GAP);
    rounds[roundIndex].forEach((match) => {
      const childCount = Math.max(match.entry_ids_parsed?.length || 1, 1);
      const children = columns[roundIndex - 1].slice(childCursor, childCursor + childCount);
      childCursor += childCount;
      const center =
        children.reduce((sum, child) => sum + child.center, 0) / Math.max(children.length, 1);
      const top = center - CARD_HEIGHT / 2;
      columns[roundIndex].push({
        ...match,
        top,
        left,
        width: CARD_WIDTH,
        height: CARD_HEIGHT,
        center,
        children: children.map((child) => child.id),
      });
    });
  }

  const connectors = [];
  for (let roundIndex = 1; roundIndex < columns.length; roundIndex += 1) {
    let childCursor = 0;
    columns[roundIndex].forEach((parent) => {
      const childCount = Math.max(parent.entry_ids_parsed?.length || 1, 1);
      const children = columns[roundIndex - 1].slice(childCursor, childCursor + childCount);
      childCursor += childCount;
      if (!children.length) return;

      const joinX = children[0].left + CARD_WIDTH + (COLUMN_GAP / 2);
      const parentX = parent.left;
      const parentY = parent.center;
      const childCenters = children.map((child) => child.center);
      const minY = Math.min(...childCenters);
      const maxY = Math.max(...childCenters);

      children.forEach((child) => {
        connectors.push({
          key: `${parent.id}-child-${child.id}`,
          x1: child.left + CARD_WIDTH,
          y1: child.center,
          x2: joinX,
          y2: child.center,
        });
      });

      if (children.length > 1) {
        connectors.push({
          key: `${parent.id}-vertical`,
          x1: joinX,
          y1: minY,
          x2: joinX,
          y2: maxY,
        });
      }

      connectors.push({
        key: `${parent.id}-parent`,
        x1: joinX,
        y1: parentY,
        x2: parentX,
        y2: parentY,
      });
    });
  }

  const flatMatches = columns.flat();
  const stageHeight = Math.max(...flatMatches.map((match) => match.top + CARD_HEIGHT), CARD_HEIGHT);
  const stageWidth = columns.length * CARD_WIDTH + Math.max(columns.length - 1, 0) * COLUMN_GAP;
  return { columns, connectors, stageWidth, stageHeight };
}
