# A3 Live E2E Test Report

**Date**: 2026-06-17 01:28:48

**Base URL**: http://127.0.0.1:8003

**Result**: 0/45 passed

---

## [FAIL] Scenario 1 - 1.Register
- **Time**: 2047ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 1 - 2.Profile-Intro
- **Time**: 2025ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: agent=? ev=0 len=54

## [FAIL] Scenario 1 - 3.Profile-Details
- **Time**: 2035ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: agent=? len=54

## [FAIL] Scenario 1 - 4.Learn-ListComp
- **Time**: 2053ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: quality=POOR len=54

## [FAIL] Scenario 1 - 5.Generate-Questions
- **Time**: 2056ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: has_q=False, len=54

## [FAIL] Scenario 1 - 6a.AnsQ1(OK)
- **Time**: 2045ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 1 - 6a.AnsQ2(OK)
- **Time**: 2055ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 1 - 6a.AnsQ3(X)
- **Time**: 2059ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 1 - 7.Evaluate
- **Time**: 2046ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: has_score=False

## [FAIL] Scenario 1 - 8.Learning-Plan
- **Time**: 2056ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: len=54

## [FAIL] Scenario 1 - 9.Check-Profile
- **Time**: 2054ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: dims_found=0

## [FAIL] Scenario 1 - 10.Check-BKT
- **Time**: 2055ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: bkt_entries=1

## [FAIL] Scenario 2 - 1.Register
- **Time**: 2042ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 2 - 2.SkipProfile-Learn
- **Time**: 2052ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: agent=? len=54

## [FAIL] Scenario 2 - 3.Algorithm-Q
- **Time**: 2041ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: advanced=False

## [FAIL] Scenario 2 - 4.BFSvsDFS
- **Time**: 2040ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: BFS=False DFS=False

## [FAIL] Scenario 2 - 5.Auto-Profile
- **Time**: 2047ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: auto_dims=0

## [FAIL] Scenario 3 - 1.Empty-422
- **Time**: 2062ms
- **Response**: s=0
- **Notes**: 

## [FAIL] Scenario 3 - 2.Spaces-422
- **Time**: 2044ms
- **Response**: s=0
- **Notes**: 

## [FAIL] Scenario 3 - 3.LongMsg
- **Time**: 2053ms
- **Response**: in=2013 out=54
- **Notes**: 

## [FAIL] Scenario 3 - 4.MixedLang
- **Time**: 2039ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: len=54

## [FAIL] Scenario 3 - 5.RapidFire
- **Time**: 6130ms
- **Response**: t=2058ms/2031ms/2039ms
- **Notes**: 

## [FAIL] Scenario 3 - 6.NotFound-404
- **Time**: 2034ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: s=0

## [FAIL] Scenario 3 - 7.Unauth-401
- **Time**: 2054ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: s=0

## [FAIL] Scenario 4 - 1.Register
- **Time**: 2048ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 4 - 2.T1-DataAnalysis
- **Time**: 2043ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: len=54

## [FAIL] Scenario 4 - 3.T2-Prereqs
- **Time**: 2043ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: coherent=False

## [FAIL] Scenario 4 - 4.T3-Recommend
- **Time**: 2047ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: coherent=False

## [FAIL] Scenario 4 - 5.History
- **Time**: 2060ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: msgs=1

## [FAIL] Scenario 5 - 1.Register
- **Time**: 2054ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 5 - 2.BuildProfile
- **Time**: 2041ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: len=54

## [FAIL] Scenario 5 - 3.GenQuestions
- **Time**: 2058ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: len=54

## [FAIL] Scenario 5 - 4a.A1(OK)
- **Time**: 2051ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 5 - 4a.A2(OK)
- **Time**: 2040ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 5 - 4a.A3(OK)
- **Time**: 2042ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 5 - 4a.A4(OK)
- **Time**: 2056ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 5 - 4a.A5(X)
- **Time**: 2041ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 5 - 4b.BKT-Batch1
- **Time**: 2046ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: entries=1

## [FAIL] Scenario 5 - 5a.Wrong1
- **Time**: 2053ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 5 - 5a.Wrong2
- **Time**: 2030ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 5 - 5a.Wrong3
- **Time**: 2035ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: 

## [FAIL] Scenario 5 - 5b.BKT-Batch2
- **Time**: 2029ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: entries=1 changed=False

## [FAIL] Scenario 5 - 6.Evaluate
- **Time**: 2052ms
- **Response**: ERR:<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>
- **Notes**: len=54

## [FAIL] Scenario 5 - 7.LearningPath
- **Time**: 2037ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: s=0

## [FAIL] Scenario 5 - 8.DebugSim
- **Time**: 2054ms
- **Response**: {'error': '<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>'}
- **Notes**: s=0
