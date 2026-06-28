# Chinese Stroke Order Generator (GIF)

> 🌟 **Live Demo & Full Dictionary:** Check out **[HanziStroke.com](https://hanzistroke.com)** - The best place to look up Chinese character stroke order, meanings, and HSK levels.
>
> 🖨️ **Need Printable Worksheets?** - This tool generates screen animations. For generating **custom PDF writing practice worksheets**, please use our [Worksheet Maker on HanziStroke.com](https://www.hanzistroke.com/worksheet-generator).

A tool to generate Chinese character stroke order animation GIFs using Hanzi Writer + Puppeteer.

## Installation

```bash
npm install
```

## Usage

Generate stroke order animation GIF for a specific Chinese character:

```bash
npm run generate 中
```

Or run directly:

```bash
node generate.js 中
```

If no character is specified, it will generate the animation for "中" by default.

Generate multiple characters from a JSON file (simple array format):

```bash
npm run batch-generate
```

`input/characters.json` example:

```json
["中", "文"]
```

The optional second argument is concurrency (default: 3).

## Output

Generated GIF files are saved in the `output/` directory with the filename format `{character}.gif`

## Configuration

You can modify the following settings in `generate.js`:

- `width`: Canvas width (default: 200)
- `height`: Canvas height (default: 200)
- `fps`: Frame rate (default: 15)
- `outputDir`: Output directory (default: ./output)

## Tech Stack

- **Hanzi Writer**: Chinese character stroke order animation rendering
- **Puppeteer**: Headless browser for recording animations
- **GIFEncoder**: GIF file generation
- **Canvas**: Image processing

