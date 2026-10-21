import { createContext, useContext } from 'react';
import { unavailableAdapter } from './contracts';
export const AuthContext = createContext(unavailableAdapter);
export function useAuth() { return useContext(AuthContext); }
