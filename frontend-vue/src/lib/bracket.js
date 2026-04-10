function safeParseEntryIds(entryIds) {
  if (Array.isArray(entryIds)) return entryIds;
  try {
    return JSON.parse(entryIds || "[]");
  } catch (_) {
    return [];
  }
}

export function makeMatches(ids) {
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

export function parseMatches(matches) {
  return (matches || []).map((match) => ({
    ...match,
    entry_ids_parsed: safeParseEntryIds(match.entry_ids),
  }));
}

export function groupMatchesIntoRounds(matches) {
  if (!matches.length) return [];
  const byRound = {};
  matches.forEach((match) => {
    if (!byRound[match.round_number]) byRound[match.round_number] = [];
    byRound[match.round_number].push(match);
  });
  return Object.keys(byRound)
    .map(Number)
    .sort((a, b) => a - b)
    .map((roundNumber) => ({
      roundNumber,
      matches: byRound[roundNumber].sort((a, b) => a.match_number - b.match_number),
    }));
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
      winner_entry_id: null,
      judge_reasoning: "",
      status: "pending",
    }));
    rounds.push({ roundNumber, matches });
    currentIds = matches.map((match) => `winner-r${roundNumber}-m${match.match_number}`);
    roundNumber += 1;
  }

  return rounds;
}

export function buildBracketLayout(
  rounds,
  {
    cardWidth = 272,
    cardHeight = 212,
    championWidth = 280,
    championHeight = 236,
    columnGap = 128,
    rowGap = 52,
    paddingX = 32,
    paddingY = 52,
    roundHeaderHeight = 64,
    roundHeaderGap = 28,
  } = {},
) {
  if (!rounds.length) {
    return {
      width: 0,
      height: 0,
      nodes: [],
      edges: [],
      roundHeaders: [],
      championNode: null,
    };
  }

  const nodes = [];
  const roundHeaders = [];
  const edges = [];
  const matchNodesByRound = [];
  const contentTop = paddingY + roundHeaderHeight + roundHeaderGap;

  const matchCardHeight = (match) => {
    const entryCount = Math.max(1, (match?.entry_ids_parsed || []).length);
    return cardHeight + Math.max(0, entryCount - 2) * 54;
  };

  let lastYBottom = contentTop + cardHeight;

  rounds.forEach((round, roundIndex) => {
    const x = paddingX + roundIndex * (cardWidth + columnGap);
    const matches = round.matches || [];
    const roundNodes = [];
    let sourceGroups = [];
    let nextY = contentTop;

    if (roundIndex > 0) {
      sourceGroups = makeMatches(matchNodesByRound[roundIndex - 1].map((node) => node.index));
    }

    matches.forEach((match, matchIndex) => {
      const height = matchCardHeight(match);
      let y = nextY;
      let centerY = y + height / 2;

      if (roundIndex > 0) {
        const prevRoundNodes = matchNodesByRound[roundIndex - 1];
        const sources = sourceGroups[matchIndex] || [];
        if (sources.length) {
          centerY = sources.reduce((sum, sourceIndex) => sum + prevRoundNodes[sourceIndex].centerY, 0) / sources.length;
          y = centerY - height / 2;
          if (roundNodes.length) {
            const previousNode = roundNodes[roundNodes.length - 1];
            const minimumY = previousNode.y + previousNode.height + rowGap;
            if (y < minimumY) {
              y = minimumY;
              centerY = y + height / 2;
            }
          } else if (y < contentTop) {
            y = contentTop;
            centerY = y + height / 2;
          }
        }
      }

      const node = {
        id: String(match.id),
        match,
        roundIndex,
        index: matchIndex,
        x,
        y,
        centerY,
        width: cardWidth,
        height,
      };

      roundNodes.push(node);
      nodes.push(node);
      nextY = node.y + node.height + rowGap;
      lastYBottom = Math.max(lastYBottom, node.y + node.height);
    });

    matchNodesByRound.push(roundNodes);
    roundHeaders.push({
      id: `round-header-${round.roundNumber}`,
      roundNumber: round.roundNumber,
      x,
      width: cardWidth,
    });

    if (roundIndex > 0) {
      const prevRoundNodes = matchNodesByRound[roundIndex - 1];
      const midpointX = x - columnGap / 2;

      roundNodes.forEach((node, matchIndex) => {
        const sources = sourceGroups[matchIndex] || [];
        sources.forEach((sourceIndex) => {
          const source = prevRoundNodes[sourceIndex];
          if (!source) return;
          edges.push({
            id: `${source.id}-${node.id}`,
            sourceId: source.id,
            targetId: node.id,
            sourceX: source.x + source.width,
            sourceY: source.centerY,
            targetX: node.x,
            targetY: node.centerY,
            midpointX,
          });
        });
      });
    }
  });

  const finalRoundNodes = matchNodesByRound[matchNodesByRound.length - 1];
  const finalNode = finalRoundNodes?.[0] || null;
  let championNode = null;

  if (finalNode) {
    championNode = {
      id: "champion-node",
      x: finalNode.x + finalNode.width + columnGap,
      y: finalNode.centerY - championHeight / 2,
      centerY: finalNode.centerY,
      width: championWidth,
      height: championHeight,
    };
    lastYBottom = Math.max(lastYBottom, championNode.y + championHeight);
    edges.push({
      id: `${finalNode.id}-champion-node`,
      sourceId: finalNode.id,
      targetId: championNode.id,
      sourceX: finalNode.x + finalNode.width,
      sourceY: finalNode.centerY,
      targetX: championNode.x,
      targetY: championNode.centerY,
      midpointX: finalNode.x + finalNode.width + columnGap / 2,
      championEdge: true,
    });
  }

  return {
    width: championNode
      ? championNode.x + championNode.width + paddingX
      : paddingX + rounds.length * cardWidth + Math.max(0, rounds.length - 1) * columnGap + paddingX,
    height: lastYBottom + paddingY,
    nodes,
    edges,
    roundHeaders,
    championNode,
  };
}
