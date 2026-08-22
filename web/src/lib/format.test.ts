import { describe, expect, it } from "vitest";

import { amount, countdown, money, percent, shortAddress } from "./format";

describe("format", () => {
  it("shows money and asset amounts the way people read them", () => {
    expect(money("1776")).toBe("$1,776.00");
    expect(amount("13.30900")).toBe("13.309");
    expect(percent(0.8034)).toBe("80.3%");
  });

  it("shortens long addresses but keeps short ones", () => {
    expect(shortAddress("0QD7ya0WKpRYHY4eKNdg4QE9J6CvVw-Ff7XNBAhj6eQOA_ML")).toBe("0QD7ya…QOA_ML");
    expect(shortAddress("short")).toBe("short");
  });

  it("formats the countdown and never goes negative", () => {
    expect(countdown(125_000)).toBe("2:05");
    expect(countdown(-5)).toBe("0:00");
  });
});
