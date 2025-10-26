'use client';

import { createContext, useContext } from 'react';

export const EmbeddedContext = createContext<boolean>(false);

export const useEmbedded = () => useContext(EmbeddedContext);
