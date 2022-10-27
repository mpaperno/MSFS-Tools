# SimConnect-Request-Tracker
##  C++ utility class for tracking and reporting `SimConnect` function invocation (request) exceptions.

`SimConnectRequestTracker` provides methods for recording and retrieving data associated with `SimConnect` function calls.

When `SimConnect` sends an exception message (`SIMCONNECT_RECV_ID_EXCEPTION`), it only provides a "send ID" with
which to identify what caused the exception in the first place. Since requests are asynchronous, there needs to
be some way to record what the original function call was in order to find out what the exception is referring to.

This utility class provides a simple way to see the actual function call and parameters which caused an exception.
It also provides a few static utility functions which may help with `SimConnect` exception handling in general.

### Requirements
* MSVC v142+ or MSFS WASM platform; C++17 or above.
* MSFS SDK with SimConnect header and library for linking.

Presumably both requirements would already be satisfied if you're working with SimConnect in the first place!

### Usage
This is a header-only "library" with one class. Simply `#include "SimConnectRequestTracker.h"` in your code.
You probably want to include it _after_ any system includes, especially `Windows.h` (or `MSFS_WindowsTypes.h` for WASM)...
but this is not required.

The public API members are fully commented in the code. Generated reference documentation is available in
Markdown: [README.cpp.md](README.cpp.md) and in HTML: [doc/index.html](doc/index.html).
A couple **usage examples** are included there.

Actual working "examples" can be found in my [WASimCommander project](https://github.com/mpaperno/WASimCommander/tree/main/src)
code, which uses the request tracker both on the WASM module (`WASimModule`) and C++ client (`WASimClient`) sides via functions
in the shared [`SimConnectHelper`](https://github.com/mpaperno/WASimCommander/blob/main/src/shared/SimConnectHelper.h) namespace.

### C# Version

I mean to publish a complete version of the tracker for use with C# as time allows. For now one could look at how I implemented
the equivalent in my _MSFS Touch Portal Plugin_ project, specifically in the
[`SimConnectService`](https://github.com/mpaperno/MSFSTouchPortalPlugin/blob/next/MSFSTouchPortalPlugin/Services/SimConnectService.cs)
class. Look for the _DLL Imports_ and _SimConnect Request Tracking_ `#region` markers.

### Copyright and Disclaimer
SimConnect-Request-Tracker<br/>
Code and documentation: Copyright Maxim Paperno, all rights reserved.

This program and associated files may be used under the terms of the GNU
General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

A copy of the GNU General Public License is included in this repository
and is also available at <http://www.gnu.org/licenses/>.
