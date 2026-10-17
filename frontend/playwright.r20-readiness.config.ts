import { defineConfig } from '@playwright/test'
export default defineConfig({testDir:'./e2e',testMatch:'r20-readiness.spec.ts',workers:1,retries:0,timeout:60000,
 reporter:[['list'],['json',{outputFile:'../artifacts/aggressive-growth-r20-20261010/r20-v2-readiness-20261013/browser-results.json'}]],
 use:{baseURL:'http://127.0.0.1:5182',headless:true,viewport:{width:1600,height:1100},trace:'off'}})
