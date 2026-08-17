const MATCH_THRESHOLD = 0.46;

export function normalizeText(value) {
  return String(value ?? '')
    .normalize('NFKC')
    .toLocaleLowerCase('zh-CN')
    .replace(/[\s\p{P}\p{S}]+/gu, '');
}

function bigrams(value) {
  const text = normalizeText(value);
  if (!text) return [];
  if (text.length === 1) return [text];
  return Array.from({ length: text.length - 1 }, (_, index) => text.slice(index, index + 2));
}

function diceSimilarity(left, right) {
  const leftParts = bigrams(left);
  const rightParts = bigrams(right);
  if (!leftParts.length || !rightParts.length) return 0;
  const remaining = new Map();
  rightParts.forEach(part => remaining.set(part, (remaining.get(part) || 0) + 1));
  let overlap = 0;
  leftParts.forEach(part => {
    const count = remaining.get(part) || 0;
    if (count > 0) {
      overlap += 1;
      remaining.set(part, count - 1);
    }
  });
  return (2 * overlap) / (leftParts.length + rightParts.length);
}

function vppsOf(operation) {
  return String(operation?.parameters?.vpps ?? operation?.vpps ?? '').trim();
}

function descriptionScore(left, right) {
  const nameScore = diceSimilarity(left?.name, right?.name);
  const leftStation = left?.station_name ?? left?.parameters?.station_name ?? '';
  const rightStation = right?.station_name ?? right?.parameters?.station_name ?? '';
  const stationScore = leftStation && rightStation ? diceSimilarity(leftStation, rightStation) : 0;
  return Math.min(0.99, nameScore * 0.9 + stationScore * 0.1);
}

function operationId(operation) {
  return String(operation?.operation_id ?? operation?.node_id ?? '');
}

export function alignOperations(leftOperations = [], rightOperations = []) {
  const exact = [];
  const consumedLeft = new Set();
  const consumedRight = new Set();
  const rightByVpps = new Map();

  rightOperations.forEach((operation, index) => {
    const vpps = vppsOf(operation);
    if (vpps) {
      const items = rightByVpps.get(vpps) || [];
      items.push({ operation, index });
      rightByVpps.set(vpps, items);
    }
  });

  leftOperations.forEach((left, leftIndex) => {
    const vpps = vppsOf(left);
    if (!vpps) return;
    const candidate = (rightByVpps.get(vpps) || []).find(item => !consumedRight.has(item.index));
    if (!candidate) return;
    consumedLeft.add(leftIndex);
    consumedRight.add(candidate.index);
    exact.push({ left, right: candidate.operation, method: 'vpps', score: 1, reasons: [`VPPS ${vpps}`] });
  });

  const fuzzyCandidates = [];
  leftOperations.forEach((left, leftIndex) => {
    if (consumedLeft.has(leftIndex)) return;
    rightOperations.forEach((right, rightIndex) => {
      if (consumedRight.has(rightIndex)) return;
      const score = descriptionScore(left, right);
      if (score >= MATCH_THRESHOLD) {
        fuzzyCandidates.push({ left, right, leftIndex, rightIndex, method: 'description', score, reasons: ['操作描述相似'] });
      }
    });
  });

  fuzzyCandidates.sort((a, b) => (
    b.score - a.score
    || operationId(a.left).localeCompare(operationId(b.left))
    || operationId(a.right).localeCompare(operationId(b.right))
  ));
  const fuzzy = [];
  fuzzyCandidates.forEach(candidate => {
    if (consumedLeft.has(candidate.leftIndex) || consumedRight.has(candidate.rightIndex)) return;
    consumedLeft.add(candidate.leftIndex);
    consumedRight.add(candidate.rightIndex);
    const { leftIndex: _leftIndex, rightIndex: _rightIndex, ...match } = candidate;
    fuzzy.push(match);
  });

  return {
    exact,
    fuzzy,
    unmatchedLeft: leftOperations.filter((_, index) => !consumedLeft.has(index)),
    unmatchedRight: rightOperations.filter((_, index) => !consumedRight.has(index)),
  };
}

export function operationSearchScore(query, operation) {
  const normalizedQuery = normalizeText(query);
  if (!normalizedQuery) return 0;
  const name = normalizeText(operation?.name);
  const vpps = normalizeText(vppsOf(operation));
  if (vpps && vpps === normalizedQuery) return 1;
  if (name.includes(normalizedQuery)) return 0.95;
  const nameScore = diceSimilarity(normalizedQuery, name);
  const vppsScore = vpps ? diceSimilarity(normalizedQuery, vpps) : 0;
  return Math.max(nameScore, vppsScore);
}

export function searchOperationCandidates(query, operations = [], limit = 8) {
  const boundedLimit = Math.max(1, Math.min(50, Number(limit) || 8));
  return operations
    .map(operation => ({ operation, score: operationSearchScore(query, operation) }))
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score || operationId(a.operation).localeCompare(operationId(b.operation)))
    .slice(0, boundedLimit);
}

export function compareRefs(leftRefs = [], rightRefs = []) {
  const left = new Set(leftRefs.filter(Boolean).map(String));
  const right = new Set(rightRefs.filter(Boolean).map(String));
  return {
    common: [...left].filter(value => right.has(value)).sort(),
    leftOnly: [...left].filter(value => !right.has(value)).sort(),
    rightOnly: [...right].filter(value => !left.has(value)).sort(),
  };
}
