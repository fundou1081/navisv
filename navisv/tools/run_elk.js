// run_elk.js - Use ELK bundled to do real layered layout
// Usage: node run_elk.js <input.json> <output.json> [--direction=DOWN|RIGHT|UP|LEFT]
//
// Reads an ELK JSON from inputPath, runs ELK.layout(), writes positioned
// JSON to outputPath. Default direction is RIGHT (horizontal flow, easiest
// to read for data-flow graphs).

const fs = require('fs');
const path = require('path');

const ELK_PATH = process.env.ELK_PATH || path.join(__dirname, '..', 'data', 'elk.bundled.js');
const ELK = require(ELK_PATH);

const [, , inputPath, outputPath, ...args] = process.argv;
if (!inputPath || !outputPath) {
  console.error('Usage: node run_elk.js <input.json> <output.json> [--direction=RIGHT]');
  process.exit(1);
}

let direction = 'RIGHT';
for (const a of args) {
  if (a.startsWith('--direction=')) {
    direction = a.split('=')[1].toUpperCase();
  }
}

const elkJson = JSON.parse(fs.readFileSync(inputPath, 'utf8'));

// Configure layered algorithm with sensible defaults for navisv
elkJson.layoutOptions = elkJson.layoutOptions || {};
elkJson.layoutOptions['elk.algorithm'] = 'layered';
elkJson.layoutOptions['elk.direction'] = direction;
elkJson.layoutOptions['elk.layered.spacing.nodeNodeBetweenLayers'] = '40';
elkJson.layoutOptions['elk.spacing.nodeNode'] = '25';
elkJson.layoutOptions['elk.spacing.edgeNode'] = '15';
elkJson.layoutOptions['elk.spacing.edgeEdge'] = '12';
elkJson.layoutOptions['elk.edgeRouting'] = 'ORTHOGONAL';
elkJson.layoutOptions['elk.layered.crossingMinimization.semiInteractive'] = 'true';
elkJson.layoutOptions['elk.layered.nodePlacement.bk.fixedAlignment'] = 'BALANCED';

const elk = new ELK();
elk.layout(elkJson).then((result) => {
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
  console.error(`OK: ${result.children?.length || 0} children, ${result.edges?.length || 0} edges`);
}).catch((err) => {
  console.error('ELK layout error:', err);
  process.exit(2);
});