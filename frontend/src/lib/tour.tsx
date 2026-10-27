import type { TourStep } from "../components/Tour";

export const TOUR_KEY = "marketrecall.tour";

export const TOUR_STEPS: TourStep[] = [
  {
    title: "Welcome to MarketRecall",
    body: (
      <>
        MarketRecall forecasts whether a Sui ecosystem token will close <b>higher or lower in 4 hours</b>. You make
        calls alongside a model that keeps its track record on Walrus. This tour takes about a minute.
      </>
    ),
    action: "Use Next and Back, or the arrow keys, to move between steps.",
  },
  {
    target: "assets",
    title: "1. Choose a token",
    body: <>Switch between <b>SUI</b>, <b>WAL</b> (the Walrus token) and <b>CETUS</b>. Everything on the page updates to the token you select.</>,
  },
  {
    target: "credits",
    title: "2. Credits",
    body: (
      <>
        You get <b>3 free credits every week</b>. Opening a session costs 1, and a correct call returns 2. Credits have
        no monetary value and cannot be purchased.
      </>
    ),
  },
  {
    target: "chart",
    title: "3. Price chart",
    body: (
      <>
        Hourly prices from Tatum. Hover to inspect any hour, and change the range from 24H to 30D. The <b>shaded area</b>
        on the right is the 4-hour window a call covers. Once you run the model, its probabilities appear there.
      </>
    ),
  },
  {
    target: "own",
    title: "4. Start with your own call",
    body: (
      <>
        Choose <b>Higher</b> or <b>Lower</b>. This opens a session for 1 credit, locks in your call, and then shows how
        the model reads the same market.
      </>
    ),
    action: "Useful for testing your own judgement against the data.",
  },
  {
    target: "model",
    title: "5. Or start with the model",
    body: (
      <>
        <b>Run the model</b> opens a session for 1 credit and shows its forecast first: the probability, the main inputs,
        and its record in similar markets. You can lock in a call afterwards.
      </>
    ),
    action: "Useful when you want the full picture before deciding.",
  },
  {
    target: "reading",
    title: "6. The forecast",
    body: (
      <>
        After you open a session, this card shows the probability <b>without memory</b> and <b>with memory</b>, the
        inputs behind it, and how often the model was right in similar conditions. Your call appears here as well.
      </>
    ),
  },
  {
    target: "chat",
    title: "7. Ask the analyst",
    body: (
      <>
        Each session includes <b>10 questions</b>, in English or Bahasa Indonesia. For example: "What is driving this
        forecast?" or "How have my past calls gone?" Answers use only your session's data, every number is checked,
        and the analyst does not give trading advice.
      </>
    ),
  },
  {
    target: "sessions",
    title: "8. Your sessions",
    body: <>All of your sessions are listed here. Select one to reopen it; you can keep asking questions for 24 hours.</>,
  },
  {
    target: "record",
    title: "9. Your record",
    body: (
      <>
        Calls resolve automatically at the end of their 4-hour window. Results are saved to <b>your own Walrus
        memory</b> and summarised here, including how you do when you agree or disagree with the model.
      </>
    ),
  },
  {
    target: "race",
    title: "10. Model track record",
    body: <>Live performance of the model with and without memory, measured by Brier score. Lower is better; a coin flip scores 0.250.</>,
  },
  {
    target: "ledger",
    title: "11. Credit history",
    body: <>Every credit change, including the weekly reset on Monday. Your balance is capped at 10.</>,
  },
  {
    title: "You're all set",
    body: (
      <>
        Choose a token, then make your call or run the model. You can reopen this tour at any time from the <b>Tour</b>
        button at the top of the page.
      </>
    ),
  },
];
