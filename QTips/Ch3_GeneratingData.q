1+1


.ql.lst: 1 2 3

.ql.lst

`EURUSD`f


1 mod `

`squares set x*x: 1 + til 10

get `squares


`squares


`var set 5


get `var

.ql.v: `var set x*x:1+til 10;

get .ql.v

get `var 

/assignment 
x*x:5+til 10

x


/ aggregating functions
prd 1+ til 10

sums 1+til 10 

///----------------------------------------------------------
/// Generate data
///----------------------------------------------------------
////// Generate: "?" operator, generate random number WITH replacement, WITH upper bound
10?10

10?neg[10] /=> domain error, negative upper limits have no meaning

/ if the upper limit is an integral number 0, q will generate random values across the whole range of positive and negative values (excluding null)
10?0j

10?0i

/ doesn't work for float
10?0f

  
/ works for temporal data as they're stored as integral values, if the value is 0 it'll generate values between 0 and a logical maximum
max 100?00:00
max 10?0D00:00:00

/ for date: an arbitrary choice of 1 leap year cycle, or 1461 days, was chosen as the upper limit
max 100?2000.01.01
min 100?2000.01.01

/ try with other dates
10?2025.01.01

/ still can't work when the value is negative
10?1991.12.18

"i"$1991.12.19



///// Deal: still "?" operator, but the left operand is Negative. Generate random number WITHOUT replacement
-10?10

/not possible to generate more numbers than the upper limit, obtain length error
-11?10

/ integral 0 still works 
-10?0j


"u"$-9?10


///// Generate single values: rand
rand 10

/generate a single byte
rand 0x0

/ check the implementation of rand 
rand

first 1?10

first
last 


////// non-numeric random data: Q allows generating random values for types other than numeric and temporal
////// since there is no natural ordering of these types, we cannot provide a maximum value 
////// instead, we must supply the null value
////// the null character can be optionally entered as 0Nc or " "
rand " "
rand 0Nc
///? what's null symbol?

/ random GUID: globally unique identifiers (GUID)
/ null GUID is: 0ng
rand 0ng
10?0ng

0x0 vs 2

/ symbols: need to use ` with a number, the number indicates the number of characters in the symbol 
5?`1

/ random selection
10?.Q.A /all the upper cases
10?.Q.a /all the lower cases
-10?.Q.n /all the numbers
10?.Q.nA /all the numbers and capital letters
10?.Q.an /alphanumeric 
10?.Q.b6 /all the characters used in base 64 encoding



////// random seed
/ the random numbers produced by q are seeded with a fixed value upon system startup 
\S /to display
\S 100 /to set
10?10
\S 10
10?10
/ commands beginning with a backslash "\" are system commands. 
/ Single letter system commands are reserved for q
/ longer names call out to the operating system for evaluation
/ These same commands can be placed in a file and executed when loading the file from a script. 

/ to dynamically generate a unique random number seed at system startup, for example, we can seed q with the number of milliseconds since midnight
/ as putting seed to 0 will make all the random numbers to be 0, we add 1 to prevent this 
system "S ", string 1+"i"$.z.T
\S

system"pwd"
.z.T
"i"$.z.T


