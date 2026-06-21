# Chapter 1. Reliable, Scalable, and Maintainable Applications


Many applications today are *data-intensive*, as opposed to *compute-intensive*. 

Many applications need to have below components:
- databases: store data so that this application, or another application, can find it again later; 
- caches: remember the result of an expensive operation, to speed up reads; 
- search indexes: allow users to search data by keyword or filter it in various ways; 
- stream processing: send a message to another process, to be handled asyncrhonously; 
- batch processing: periodically crunch a large amount of accumulated data. 

There are many database systems with different characteristics, because different applications have different requirements. 

This book focuses on three concerns that are important in most software systems:
- **Reliability**: The system should ocntinue to work *correctly* (performing the correct function at the desired level of performance) even in the face of *adversity* (hardware of software faults, and even human error). 
- **Scalability**: As the system grows (in data volume, traffic volume, or complexity), there should be reasonable ways of dealing with that growth. 
- **Maintainability**: Peope working on the system over time are able to work on it productively (eg: engineering and operations maintian current behaviour of the system and adapt the system to new use cases). 

## Reliability 

Meaning: continue to work correctly, even when things go wrong. 

Things can go wrong are called "faults", systems that anticipate faults and can cope with them are called *fault-tolerant* (tolerate certain types of faults) or *resilient*. 

Fault is not failure:
- A fault is usually defined as one component of the system deviating from its spec;
- A failure is when the system as a whole stops providing the required servie to the user. 


Examples of faults:
- Hardware faults
    - Examples: hard disks crash, RAM becomes faulty, the power grid has a blackout. 
    - How to solve it?
        - add redundancy to the individual hardware components to reduce the failure rate of the system
        - However due to data volume and applications' computing demands increase, more applications started using larger number of machines, which increases the rate of hardware faults. 
        - hence move toward systems that can tolerate the loss of entire machines, by using software fault-tolerance techniques in preference or in addition to hardware redundancy. 

- Software Errors
    - Hardware errors usually have weak correlation, however software errors are usually systematic. 
    - The software is making some assumptions about its environment, and these assumtpions stop being true for some reason, which caused software errors. 
    - No quick for solution here, lots of small things can help: carefully thinking about assumptions and interactions in the system; thorough testing; process isolation; allowing processes to crash and restart; measuring, monitoring and analyzing system behaviour in product, etc. 
    - If a system is expected to provide some guarantee, it can constantly check itself while it is running and raise an alert if a discrepancy is found. 


- Human Errors; 
    - Humans are known to be unreliable. One study shows configurations errors by operators were the leading cause of outages. 
    - How to make systems reliable in spite of human errors? 
        - Design systems in a way that minimizes oppportunities for error. For example, well-designed abstractions, APIs, and admin interfaces make it easy to do "the right thing" and discourage "the wrong thing". However the balance between restrictions and flexibility is tricky. 
        - Decouple the places where people make the most mistakes from the places where they can cause failures. In particular, provide fully featured non-production *sandbox* environments. 
        - Test thoroughly at all levels, from unit tests to whole-system integration tests and manual tests. 
        - Allow quick and easy recovery from human errors, to minimize the impact in the case of a failure. Eg: fast roll back, roll out new code gradually, provide tools to recompute data. 
        - Set up detailed and clear monitoring, eg: performance metric and error rates. In other engineering disciplines this is referred to as *telemetry*. 
        - Implement good management practices and training. 


## Scalability 
Meaning: describe a system's ability to cope with increased load. 

Discussing scalability means considering questions like:
- If the system grows in a particular way, what are our options for coping with the growth?
- How can we add computing resources to handle the additional load?

### Describe Load
Firstly we need to succinctly describe the current load on the system. Load can be described with **load parameters**. The coice of parameters depends on the architecture of the system, eg:
- number of requests per second to a web server
- the ratio of reads to writes in a database
- the number of simultaneously active users in a chat room
- the hit rate on a cache


### Describe Performance

Once the system load is described, we can investigate what happens when the load increases, in two ways:
- When we increase a load parameter and keep the system resources (CPU, memory, network bandwidth, etc.) unchanged, how is the performance of your system affected? 
- when we increase a load parameter, how much do you need to increase the resource if you want to keep performance unchanged? 

To describe the performance of a system:
- Batch processing system: throughput, the number of records we can process per second, or the total time it takes to run a job on a dataset of a certain size.
- Online system: response time, the time between a client sending a request and receiving a response. 


P.S.: *Latency* and *response time*:
- Response time: what the client sees: besides the actually time to process the request (the *service time*), it includes network delays and queueing delays. 
- Latency: the duration that a request is waiting to be handled, during which it is latent, awaiting service. 



As each time the response time vary depending on the noise and environment, hence we need to consider response time as a **distribution** of values that we can measure, eg: median, percentiles. 

High percentiles of response time, also known as *tail latencies*, are important because they directly affect users' experience of the service. 

Percentiles are often used in *service level objectives (SLOs)* and *service level agreements (SLAs)*, contracts that define the expected performance and availability of a service. 

*Queueing delays* often accounts for a large part of the response time at high percentiles.
- *Head-of-line blocking*: As a server can only process a small number of things in parallel, it only takes a small number of slow requests to hold up the processing of subsequent requests. Hence even if subsequent requests are fast to process, the client will still see overall slow response time due to the time waiting for the prior requests to complete. So it is important to measure response times on the client side. 


### Approaches for Coping with Load
- Scaling up: vertical scaling, moving to a more powerful machine;
- Scaling out: horizontal scaling, distributing the load across multiple smaller machines. 

Good architectures usually involve a pragmatic mixture of approaches. 

An architecture that scales well for a particular appication is built around assumptions of which operations will be common and which will be rare - the load parameters. If those assumptions turn out to be wrong, the engineering effort for scaling is at best wasted, and at worst counterproductive. In an early-stage startup or an unproven product it's usually more important to be able to iterate quickly on product features than it is to scale to some hypothetical future load. 

## Maintainability 

### Operability 
Meaning: Make it easy for operations teams to keep the system running smoothly. 

"Good operations can often work around the limitations of bad (or incomplete) software, but good software cannot run reliably with bad oeprations."

Operations teams are vital to keeping a software system running smoothly. A good operations team typically is responsible for the following (and more): 
- Monitoring the health of the system and quickly restoring service if it goes into a bad state
- Tracking down the cause of problems, such as system failures or degraded performance
- Keeping software and platforms up to date, including security patches
- Keeping tabs on how different systems affect each other, so that a problematic change can be avoided before it causes damage
- Anticipating future problems and solving them befroe they occur (eg: capacity planning)
- Establishing good practices and tools for deployment, configuration management and more
- Performing complex maintenance tasks, such as moving an application from one platform to another
- Maintaining the security of the system as configuration changes are made
- Defining processes that make operations predictable and help keep the production environment stable
- Preserving the organization's knowledge about the system, even as individual people come and go

Data systems can do various things to make routine tasks easy, including:
- Providing visibility into the runtime behaviour and internals of the system, with good monitoring 
- Providing good support for automation and integration with standard tools
- Avoiding dependency on individual machines (allowing machines to be taken down for maintenance while the system as a whole continues running uninterrupted)
- Providing good documentation and an easy-to-understand operational model 
- Providing good default behaviour, but also giving administrators the freedom to override defaults when needed
- Self-healing where appropriate, but also giving administrators manual control over the system state when needed
- Exhibiting predictable behaviour, minimizing surprises





### Simplicity
Make it easy for new engineers to understand the system, by removing as much complexity as possible from the system.

Possible symptoms of complexity:
- explosion of the state space
- tight coupling of modules
- tangled dependencies
- inconsistent naming and terminology
- hacks aimed at solving performance issues
- special-casing to work around issues elsewhere

Reducing complexity greatly improves the maintainability of software. Making a system simpler does not necessarily mean reducing its functionality, it can also mean removing *accidental complexity*, defined as it is not inherent in the problem that the software solves but arises only from the implementation. 


### Evolvability 
Make it easy for engineers to make changes to the system in the future, adapting it for unanticipated use cases as requirements change. Also known as *extensibility*, *mobility*, or *plasticity*. 





