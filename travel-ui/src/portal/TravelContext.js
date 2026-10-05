import { createContext, useContext } from "react";

export const TravelContext = createContext(null);

export function useTravel() {
  const value = useContext(TravelContext);
  if (!value) throw new Error("TravelContext is missing");
  return value;
}
