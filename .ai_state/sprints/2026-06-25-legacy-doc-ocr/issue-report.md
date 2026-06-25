# Legacy .doc OCR Routes To Manual

## Phenomenon

Production tender project document extraction failed with `JSONContractError`.
The visible model output looked like non-JSON text or `<tool_call>` style output, but the
project document context was effectively empty.

## Reproduction Signal

- File: `knowledge/external/张謇企业家学院/张謇企业家学院网络学院直播间建设项目公开招标文件.doc`
- Bad stored text shape: a short manual placeholder like
  `### 文件: ...公开招标文件.doc (kind=manual, route=manual)`
- Expected stored text: native Word extraction with tens of thousands of characters,
  including scoring and price markers.

## Expected

Legacy `.doc` files with a text layer should be treated as Word documents and read
natively before OCR/model extraction.

## Actual

`.doc` was not part of the Word/native classifier path and fell through to manual
placeholder text, starving `tender-extract-info` of the招标文件 scoring context.
