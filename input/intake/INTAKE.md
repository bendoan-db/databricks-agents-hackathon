**Business Discovery**

1. What business outcome are you trying to improve? How do you solve this problem today without ML/AI? What's the cost of the current approach?  
2. What decision does this model inform? What happens when that decision is wrong?  
3. Who owns this problem \- which team, which budget?  
4. Is there executive sponsorship? What's the visibility level?

**Technical Discovery**

5. What is the **task** you are trying to accomplish with GenAI? (Chatbot, workflow, etc.) Be as descriptive as possible.  
6. Walk through the current process you are trying to automate/agentify. Include any external systems and integrations you need to support this.

**Unstructured Data Retrieval**

7. What unstructured data (documents) do you want to provide to the GenAI application to accomplish this task?  
   1. What is the size/quality/format of these documents?  
      1. How many documents?  
      2. How many pages?  
   2. Does this data contain PII/PHI? Any restrictions on where it can go?  
8. Do these documents have any complex elements that need to be extracted? Figures, charts, images, etc.). If yes, please describe them  
9. **Can you provide us document samples?**

**Structured Data Retrieval**

10. What structured data (data tables) do you want to provide to the GenAI application to accomplish this task?  
    1. How clean is the source data? Any known gaps, nulls, or quality issues?  
    2. Does this data contain PII/PHI? Any restrictions on where it can go?  
11. What are some examples of how this data is to be queried to accomplish the task?  
12. Can you provide us with example records or table schema(s)?

**Evaluation**

13. Do you have a way to evaluate the effectiveness of your application?  
    1. **Do you have a set of benchmark questions or target outputs to evaluate against?** If yes, please provide them.  
    2. **Do you have target metrics for this application?** Some examples:   
       1. Answer correctness  
       2. Document recall/relevance  
       3. Text2SQL correctness  
       4. Other custom metrics

**Inference**

14. Who sees the agent output \- analysts, business users, customers, or systems? How do they consume it \- dashboard, API, embedded in an app, batch report?  
15. What action do they take based on the prediction/output?  
16. What's the latency requirement \- real-time response or next-day batch is fine?  
17. Do you have any of the following advanced requirements (note: if they don’t know what these are, then the answer is no)  
    1. Agent memory, thread-scoped memory, agent state  
    2. Multi-modal (image-based) inputs/outputs  
18. Do you have any workspace-specific restrictions on networking?  
    1. PrivateLink  
    2. Firewall  
    3. Public internet ingress/egress