# Demo video script (about 3 minutes)

Record the screen at 1080p with your own voice. Speak plainly; the numbers do the work. Each line below is roughly what to say; the bracket says what is on screen.

## 0:00 to 0:20: the number

[Landing page, headline visible]

"There are 3.16 million models on Hugging Face. We put all of them in one FalkorDB graph. 48,975 models say apache or MIT while a model they were built on carries restricted terms. 11,442 of them say commercial use is fine when an ancestor says it isn't. Only 346 ship a license file."

## 0:20 to 0:50: three hops up

[Click kenpath/svara-tts-v1]

"This is a text-to-speech model with a hundred thousand downloads a month. It says apache-2.0. FinePrint walks up the tree: an adapter on a fine-tune of a fine-tune of Llama 3.2. So the Llama 3.2 terms come with it: ship the agreement, show Built with Llama, start the name with Llama."

[Toggle "Direct parents only"]

"This is what the model page shows you: one hop. From here it looks clean."

## 0:50 to 1:15: block for commercial use

[Click ifmylove2011/girlslike, use = commercial]

"A FLUX LoRA that says apache. FLUX.1 dev is non-commercial, and its terms apply to every derivative. For a commercial product the answer is block. Here are clean models of the same task and size instead."

## 1:15 to 1:45: the agent reads the card

[Click TheBloke/LeoScorpius-GreenNode-Alpaca-7B-v1-GGUF, press "Read the card"]

"The Hub tags say this is clean. The agent reads the model card, finds that the original was fine-tuned on tatsu-lab/alpaca, quotes the sentence, and writes that edge into the graph on the model the card is talking about. Alpaca is non-commercial. The verdict changes. The agent never writes a query and never decides the verdict; it only adds evidence the rules can check."

## 1:45 to 2:15: the agent acts in your code

[Terminal: a coding agent session in a small repo with the FinePrint MCP server and hook installed. Ask it to add `ifmylove2011/girlslike` to the project.]

"Same check inside a coding agent. It tries to pull the FLUX LoRA. The guard stops the download, the agent asks FinePrint for a clean substitute, swaps it in, and drafts the notice file. In CI, `fineprint check` fails the build the same way."

## 2:15 to 2:45: why it needs a graph

[Landing page findings: PageRank list, relicensing points, Hub API comparison]

"Finding every descendant of Llama 3.1 8B through the Hugging Face API takes twenty-one thousand calls, close to four hours. FalkorDB does it in 70 milliseconds. PageRank over the whole Hub says the most load-bearing model is FLUX.1 dev, which is non-commercial. And 54% of the mismatches carry the exact tags of one fine-tuning library's card template, which writes apache-2.0 on everything. We wrote the one-line fix."

## 2:45 to 3:00: close

[README eval table]

"On a sealed set of 120 models, an LLM reading the card called eight restricted models clean. FinePrint called none of them clean, and found every case where the terms sit two or more hops up. Every fine-tune comes with fine print. FinePrint reads it."
